using System.Text.Json.Serialization;

namespace Gateway.Dto;

public class ChatRequest
{
    public string Soru { get; set; } = string.Empty;

    [JsonPropertyName("ek_bilgi")]
    public string EkBilgi { get; set; } = string.Empty;

    [JsonPropertyName("ek_soru")]
    public string EkSoru { get; set; } = string.Empty;

    [JsonPropertyName("ek_soru_yanitlandi")]
    public bool EkSoruYanitlandi { get; set; }
}
