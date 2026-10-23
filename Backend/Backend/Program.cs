using DiscordBot_API.Data;
using DiscordBot_API.Middleware;
using Microsoft.AspNetCore.Diagnostics;
using Microsoft.EntityFrameworkCore;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddDbContext<AppDbContext>(options =>
    options.UseNpgsql(builder.Configuration.GetConnectionString("DefaultConnection")));
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen();

var app = builder.Build();

if (string.IsNullOrWhiteSpace(app.Configuration["ApiKey"]))
{
    if (!app.Environment.IsDevelopment())
        throw new InvalidOperationException("Не задан ApiKey. Укажите его в конфиге или переменной окружения ApiKey.");

    app.Logger.LogWarning("ApiKey не задан: авторизация отключена (допустимо только в Development).");
}

app.UseExceptionHandler(errorApp => errorApp.Run(async context =>
{
    var exceptionFeature = context.Features.Get<IExceptionHandlerFeature>();
    if (exceptionFeature?.Error != null)
    {
        app.Logger.LogError(exceptionFeature.Error, "Необработанное исключение при запросе {Path}", context.Request.Path);
    }

    context.Response.StatusCode = StatusCodes.Status500InternalServerError;
    await context.Response.WriteAsJsonAsync(new { message = "Внутренняя ошибка сервера." });
}));

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

if (app.Configuration.GetValue("AutoMigrate", true))
{
    using var scope = app.Services.CreateScope();
    scope.ServiceProvider.GetRequiredService<AppDbContext>().Database.Migrate();
}

app.UseMiddleware<ApiKeyMiddleware>();

app.MapGet("/api/health", async (AppDbContext db) =>
    await db.Database.CanConnectAsync()
        ? Results.Ok(new { status = "ok" })
        : Results.StatusCode(StatusCodes.Status503ServiceUnavailable));

app.MapControllers();
app.Run();