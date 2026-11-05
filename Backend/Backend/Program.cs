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

// Безопасная инициализация и обновление схемы БД при старте
using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<AppDbContext>();
    try
    {
        if (app.Configuration.GetValue("AutoMigrate", true))
        {
            db.Database.Migrate();
        }
    }
    catch (Exception ex)
    {
        app.Logger.LogWarning(ex, "Колонки уже существуют. Применяем безопасную синхронизацию схемы.");
    }

    try
    {
        db.Database.ExecuteSqlRaw("""
            ALTER TABLE "ServerConfigs" ADD COLUMN IF NOT EXISTS "WelcomeTitle" text;
            ALTER TABLE "ServerConfigs" ADD COLUMN IF NOT EXISTS "WelcomeDescription" text;
            ALTER TABLE "ServerConfigs" ADD COLUMN IF NOT EXISTS "VoiceGeneratorChannelId" character varying(32);
            ALTER TABLE "ServerConfigs" ADD COLUMN IF NOT EXISTS "VoiceRoomTemplate" character varying(64);
            ALTER TABLE "ServerConfigs" ADD COLUMN IF NOT EXISTS "AiEnabled" boolean NOT NULL DEFAULT true;
            ALTER TABLE "ServerConfigs" ADD COLUMN IF NOT EXISTS "AiMode" character varying(32) DEFAULT 'standard';
            ALTER TABLE "ServerConfigs" ADD COLUMN IF NOT EXISTS "AiCustomScenario" text;
            ALTER TABLE "ServerConfigs" ADD COLUMN IF NOT EXISTS "AiCustomRules" text;
        """);
    }
    catch (Exception ex)
    {
        app.Logger.LogError(ex, "Ошибка при проверке дополнительных колонок БД.");
    }
}

app.UseMiddleware<ApiKeyMiddleware>();

app.MapGet("/api/health", async (AppDbContext db) =>
    await db.Database.CanConnectAsync()
        ? Results.Ok(new { status = "ok" })
        : Results.StatusCode(StatusCodes.Status503ServiceUnavailable));

app.MapControllers();
app.Run();