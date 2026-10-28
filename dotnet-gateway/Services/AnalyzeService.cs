using System.Text.Json;
using Microsoft.AspNetCore.Http.Features;
using Gateway.Dto;
using Gateway.Exceptions;
using Microsoft.Extensions.Options;
using Gateway.Config;

namespace Gateway.Services;

public class AnalyzeService
{
    private readonly HttpClient _httpClient;
    private readonly PythonServiceSettings _settings;
    private readonly ILogger<AnalyzeService> _logger;

    public AnalyzeService(HttpClient httpClient, IOptions<PythonServiceSettings> settings, ILogger<AnalyzeService> logger)
    {
        _httpClient = httpClient;
        _settings = settings.Value;
        _logger = logger;
    }

    public async Task<AnalyzeResponse> AnalyzeAsync(ChatRequest request, CancellationToken cancellationToken = default)
    {
        _logger.LogInformation("Python servisine analiz istegi gonderiliyor");

        try
        {
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            cts.CancelAfter(TimeSpan.FromSeconds(_settings.TimeoutSeconds));

            using var httpResponse = await _httpClient.PostAsJsonAsync(_settings.AnalyzePath, request, cts.Token);

            if (!httpResponse.IsSuccessStatusCode)
            {
                var code = (int)httpResponse.StatusCode;
                _logger.LogError("Python servisi {Code} dondu", code);

                var userMsg = code switch
                {
                    422 => "Gecersiz soru formati",
                    503 => "AI servisi gecici olarak hizmet veremiyor",
                    _ => $"AI servisi bir hatayla karsilasti (kod: {code})"
                };

                throw new PythonServiceException(code, userMsg);
            }

            var response = await httpResponse.Content.ReadFromJsonAsync<AnalyzeResponse>(cts.Token);

            if (response == null)
            {
                throw new PythonServiceException(502, "Python servisi bos cevap dondu");
            }

            var found = response.BulunanMaddeNumaralari?.Count ?? 0;
            _logger.LogInformation("Python cevabi alindi, {Found} madde bulundu", found);
            return response;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (PythonServiceException)
        {
            throw;
        }
        catch (HttpRequestException ex)
        {
            _logger.LogError("Python servisine ulasilamadi: {Message}", ex.Message);
            throw new PythonServiceException(503, "AI servisi su anda erisilemez durumda. Lutfen daha sonra tekrar deneyin.");
        }
        catch (TaskCanceledException)
        {
            _logger.LogError("Python servisi timeout: {Timeout} sn", _settings.TimeoutSeconds);
            throw new PythonServiceException(504, "AI servisi cevap vermedi (timeout)");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Beklenmeyen hata");
            throw new PythonServiceException(500, "AI servisi iletisiminde beklenmeyen hata");
        }
    }

    public async Task AnalyzeStreamAsync(ChatRequest request, HttpResponse response, CancellationToken cancellationToken)
    {
        using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        cts.CancelAfter(TimeSpan.FromSeconds(_settings.TimeoutSeconds));
        try
        {
            using var message = new HttpRequestMessage(HttpMethod.Post, _settings.AnalyzePath.TrimEnd('/') + "/stream")
            {
                Content = JsonContent.Create(request)
            };
            message.Headers.Accept.Clear();
            message.Headers.Accept.ParseAdd("text/event-stream");
            using var upstream = await _httpClient.SendAsync(message, HttpCompletionOption.ResponseHeadersRead, cts.Token);
            if (!upstream.IsSuccessStatusCode)
                throw new PythonServiceException((int)upstream.StatusCode, "Analiz servisi istegi tamamlayamadi.");
            if (upstream.Content.Headers.ContentType?.MediaType != "text/event-stream")
                throw new PythonServiceException(502, "Analiz servisinden beklenmeyen yanit alindi.");

            response.ContentType = "text/event-stream; charset=utf-8";
            response.Headers.CacheControl = "no-cache, no-transform";
            response.Headers["X-Accel-Buffering"] = "no";
            response.HttpContext.Features.Get<IHttpResponseBodyFeature>()?.DisableBuffering();
            await using var input = await upstream.Content.ReadAsStreamAsync(cts.Token);
            var buffer = new byte[4096];
            int read;
            while ((read = await input.ReadAsync(buffer, cts.Token)) > 0)
            {
                await response.Body.WriteAsync(buffer.AsMemory(0, read), cts.Token);
                await response.Body.FlushAsync(cts.Token);
            }
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            // Tarayici ayrildi veya sohbet silindi; yukaridaki using upstream'i de kapatir.
        }
        catch (Exception error)
        {
            _logger.LogWarning("Analiz akisi tamamlanamadi: {ErrorType}", error.GetType().Name);
            var userMessage = error is OperationCanceledException
                ? "Analiz zaman sinirina ulasti. Gorunen metin kismi yanittir."
                : "Analiz baglantisi kesildi. LM Studio ve Python servisini kontrol edin.";
            if (!response.HasStarted)
                throw new PythonServiceException(error is PythonServiceException serviceError ? serviceError.StatusCode : 503, userMessage);
            var data = JsonSerializer.Serialize(new { type = "error", message = userMessage });
            await response.WriteAsync($"data: {data}\n\n", cancellationToken);
            await response.Body.FlushAsync(cancellationToken);
        }
    }
}
