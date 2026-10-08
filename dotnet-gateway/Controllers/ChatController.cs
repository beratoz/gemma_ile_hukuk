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

        var response = await _analyzeService.AnalyzeAsync(request);
        return Ok(response);
    }
}
