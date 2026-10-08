using System.Net;
using System.Text.Json;
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

    public async Task<AnalyzeResponse> AnalyzeAsync(ChatRequest request)
    {
        _logger.LogInformation("Python servisine analiz istegi gonderiliyor: '{Soru}'", request.Soru);

        try
        {
            using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(_settings.TimeoutSeconds));

            var httpResponse = await _httpClient.PostAsJsonAsync(_settings.AnalyzePath, request, cts.Token);

            if (!httpResponse.IsSuccessStatusCode)
            {
                var body = await httpResponse.Content.ReadAsStringAsync(cts.Token);
                var code = (int)httpResponse.StatusCode;
                _logger.LogError("Python servisi {Code} dondu: {Body}", code, body);

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
}
