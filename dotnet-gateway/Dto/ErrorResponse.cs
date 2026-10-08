namespace Gateway.Dto;

public class ErrorResponse
{
    public int Status { get; set; }
    public string Error { get; set; } = string.Empty;
    public string Message { get; set; } = string.Empty;
    public DateTimeOffset Timestamp { get; set; }

    public static ErrorResponse Of(int status, string error, string message)
    {
        return new ErrorResponse
        {
            Status = status,
            Error = error,
            Message = message,
            Timestamp = DateTimeOffset.UtcNow
        };
    }
}
