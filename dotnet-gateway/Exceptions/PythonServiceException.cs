namespace Gateway.Exceptions;

public class PythonServiceException : Exception
{
    public int StatusCode { get; }

    public PythonServiceException(int statusCode, string message) : base(message)
    {
        StatusCode = statusCode;
    }
}
