package com.berat.legaltech.gateway.service;

import com.berat.legaltech.gateway.dto.AnalyzeResponse;
import com.berat.legaltech.gateway.dto.ChatRequest;
import com.berat.legaltech.gateway.exception.PythonServiceException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatusCode;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientRequestException;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

@Service
public class AnalyzeService {

    private static final Logger log = LoggerFactory.getLogger(AnalyzeService.class);

    private final WebClient pythonWebClient;
    private final String analyzePath;
    private final int timeoutSeconds;

    public AnalyzeService(
            WebClient pythonWebClient,
            @Value("${python.service.analyze-path}") String analyzePath,
            @Value("${python.service.timeout-seconds}") int timeoutSeconds
    ) {
        this.pythonWebClient = pythonWebClient;
        this.analyzePath = analyzePath;
        this.timeoutSeconds = timeoutSeconds;
    }

    public AnalyzeResponse analyze(ChatRequest request) {
        log.info("Python servisine analiz istegi gonderiliyor: '{}'", request.soru());

        try {
            AnalyzeResponse response = pythonWebClient.post()
                    .uri(analyzePath)
                    .bodyValue(request)
                    .retrieve()
                    .onStatus(HttpStatusCode::isError, this::mapHttpError)
                    .bodyToMono(AnalyzeResponse.class)
                    .timeout(Duration.ofSeconds(timeoutSeconds))
                    .block();

            if (response == null) {
                throw new PythonServiceException(502, "Python servisi bos cevap dondu");
            }

            int found = response.bulunanMaddeNumaralari() == null ? 0 : response.bulunanMaddeNumaralari().size();
            log.info("Python cevabi alindi, {} madde bulundu", found);
            return response;

        } catch (PythonServiceException e) {
            throw e;
        } catch (WebClientRequestException e) {
            log.error("Python servisine ulasilamadi: {}", e.getMessage());
            throw new PythonServiceException(503, "AI servisi su anda erisilemez durumda. Lutfen daha sonra tekrar deneyin.");
        } catch (Exception e) {
            if (e.getCause() instanceof TimeoutException || e instanceof TimeoutException) {
                log.error("Python servisi timeout: {} sn", timeoutSeconds);
                throw new PythonServiceException(504, "AI servisi cevap vermedi (timeout)");
            }
            log.error("Beklenmeyen hata", e);
            throw new PythonServiceException(500, "AI servisi iletisiminde beklenmeyen hata");
        }
    }

    private Mono<? extends Throwable> mapHttpError(ClientResponse response) {
        return response.bodyToMono(String.class)
                .defaultIfEmpty("")
                .map(body -> {
                    int code = response.statusCode().value();
                    log.error("Python servisi {} dondu: {}", code, body);
                    String userMsg = switch (code) {
                        case 422 -> "Gecersiz soru formati";
                        case 503 -> "AI servisi gecici olarak hizmet veremiyor";
                        default  -> "AI servisi bir hatayla karsilasti (kod: " + code + ")";
                    };
                    return new PythonServiceException(code, userMsg);
                });
    }
}
