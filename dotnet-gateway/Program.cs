using FluentValidation;
using Gateway.Config;
using Gateway.Middleware;
using Gateway.Services;

var builder = WebApplication.CreateBuilder(args);

var pythonSection = builder.Configuration.GetSection("PythonService");
builder.Services.Configure<PythonServiceSettings>(pythonSection);

var pythonSettings = pythonSection.Get<PythonServiceSettings>()!;

builder.Services.AddHttpClient<AnalyzeService>(client =>
{
    client.BaseAddress = new Uri(pythonSettings.BaseUrl);
    client.DefaultRequestHeaders.Add("Accept", "application/json");
    client.Timeout = TimeSpan.FromSeconds(pythonSettings.TimeoutSeconds);
});

builder.Services.AddValidatorsFromAssemblyContaining<Program>();

builder.Services.AddExceptionHandler<GlobalExceptionHandler>();
builder.Services.AddProblemDetails();

var allowedOrigins = builder.Configuration.GetSection("Cors:AllowedOrigins").Get<string[]>() ?? Array.Empty<string>();

builder.Services.AddCors(options =>
{
    options.AddDefaultPolicy(policy =>
    {
        policy.WithOrigins(allowedOrigins)
              .WithMethods("GET", "POST", "PUT", "DELETE", "OPTIONS")
              .AllowAnyHeader()
              .AllowCredentials()
              .SetPreflightMaxAge(TimeSpan.FromSeconds(3600));
    });
});

builder.Services.AddControllers();

var app = builder.Build();

app.UseExceptionHandler(_ => { });
app.UseCors();
app.MapControllers();

app.Run();
