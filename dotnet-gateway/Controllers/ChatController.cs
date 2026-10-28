using FluentValidation;
using Gateway.Dto;
using Gateway.Services;
using Microsoft.AspNetCore.Mvc;

namespace Gateway.Controllers;

[ApiController]
[Route("api")]
public class ChatController : ControllerBase
{
    private readonly AnalyzeService _analyzeService;
    private readonly IValidator<ChatRequest> _validator;

    public ChatController(AnalyzeService analyzeService, IValidator<ChatRequest> validator)
    {
        _analyzeService = analyzeService;
        _validator = validator;
    }

    [HttpPost("chat")]
    public async Task<IActionResult> Chat([FromBody] ChatRequest request)
    {
        var validationResult = await _validator.ValidateAsync(request);
        if (!validationResult.IsValid)
        {
            var message = string.Join("; ", validationResult.Errors.Select(e => $"{e.PropertyName}: {e.ErrorMessage}"));
            return BadRequest(ErrorResponse.Of(400, "Bad Request", message));
        }

        var response = await _analyzeService.AnalyzeAsync(request, HttpContext.RequestAborted);
        return Ok(response);
    }

    [HttpPost("chat/stream")]
    public async Task Stream([FromBody] ChatRequest request)
    {
        var validationResult = await _validator.ValidateAsync(request, HttpContext.RequestAborted);
        if (!validationResult.IsValid)
        {
            Response.StatusCode = 400;
            var message = string.Join("; ", validationResult.Errors.Select(error => error.ErrorMessage));
            await Response.WriteAsJsonAsync(ErrorResponse.Of(400, "Bad Request", message), HttpContext.RequestAborted);
            return;
        }
        await _analyzeService.AnalyzeStreamAsync(request, Response, HttpContext.RequestAborted);
    }
}
