using System.Text.Json.Serialization;

namespace Gateway.Dto;

public class AnalyzeResponse
{
    [JsonPropertyName("soru")]
    public string Soru { get; set; } = string.Empty;

    [JsonPropertyName("cikarilan_kavramlar")]
    public List<string> CikarilanKavramlar { get; set; } = new();

    [JsonPropertyName("bulunan_madde_numaralari")]
    public List<string> BulunanMaddeNumaralari { get; set; } = new();

    [JsonPropertyName("mutalaa")]
    public string Mutalaa { get; set; } = string.Empty;
}
