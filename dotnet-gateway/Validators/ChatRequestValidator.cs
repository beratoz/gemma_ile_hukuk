using FluentValidation;
using Gateway.Dto;

namespace Gateway.Validators;

public class ChatRequestValidator : AbstractValidator<ChatRequest>
{
    public ChatRequestValidator()
    {
        RuleFor(x => x.Soru)
            .NotEmpty().WithMessage("Soru bos olamaz")
            .MinimumLength(3).WithMessage("Soru 3-2000 karakter arasinda olmali")
            .MaximumLength(2000).WithMessage("Soru 3-2000 karakter arasinda olmali");
    }
}
