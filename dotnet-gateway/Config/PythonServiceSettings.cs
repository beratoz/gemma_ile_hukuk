namespace Gateway.Config;

public class PythonServiceSettings
{
    public string BaseUrl { get; set; } = string.Empty;
    public string AnalyzePath { get; set; } = string.Empty;
    public int TimeoutSeconds { get; set; }
}
