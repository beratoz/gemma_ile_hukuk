using Gateway.Dto;
using Gateway.Exceptions;
using Microsoft.AspNetCore.Diagnostics;

namespace Gateway.Middleware;

public class GlobalExceptionHandler : IExceptionHandler
{
    private readonly ILogger<GlobalExceptionHandler> _logger;

    public GlobalExceptionHandler(ILogger<GlobalExceptionHandler> logger)
    {
        _logger = logger;
    }

    public async ValueTask<bool> TryHandleAsync(HttpContext httpContext, Exception exception, CancellationToken cancellationToken)
    {
        ErrorResponse errorResponse;
        int statusCode;

        switch (exception)
        {
            case PythonServiceException pythonEx:
                statusCode = pythonEx.StatusCode;
                if (statusCode < 400 || statusCode > 599) statusCode = 502;
                errorResponse = ErrorResponse.Of(statusCode, ReasonPhrase(statusCode), pythonEx.Message);
                break;

            default:
                _logger.LogError(exception, "Beklenmeyen sunucu hatasi");
                statusCode = 500;
                errorResponse = ErrorResponse.Of(500, "Internal Server Error", "Sunucuda beklenmeyen bir hata olustu");
                break;
        }

        httpContext.Response.StatusCode = statusCode;
        await httpContext.Response.WriteAsJsonAsync(errorResponse, cancellationToken);
        return true;
    }

    private static string ReasonPhrase(int statusCode)
    {
        return statusCode switch
        {
            400 => "Bad Request",
            401 => "Unauthorized",
            403 => "Forbidden",
            404 => "Not Found",
            422 => "Unprocessable Entity",
            500 => "Internal Server Error",
            502 => "Bad Gateway",
            503 => "Service Unavailable",
            504 => "Gateway Timeout",
            _ => "Error"
        };
    }
}
