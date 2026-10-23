using System.Security.Cryptography;
using System.Text;

namespace DiscordBot_API.Middleware;

public class ApiKeyMiddleware
{
    public const string HeaderName = "X-Api-Key";

    private readonly RequestDelegate _next;
    private readonly byte[]? _expectedKeyHash;

    public ApiKeyMiddleware(RequestDelegate next, IConfiguration configuration)
    {
        _next = next;
        var key = configuration["ApiKey"];
        _expectedKeyHash = string.IsNullOrWhiteSpace(key)
            ? null
            : SHA256.HashData(Encoding.UTF8.GetBytes(key));
    }

    public async Task InvokeAsync(HttpContext context)
    {
        var path = context.Request.Path;
        if (_expectedKeyHash == null
            || path.StartsWithSegments("/api/health")
            || path.StartsWithSegments("/swagger"))
        {
            await _next(context);
            return;
        }

        if (context.Request.Headers.TryGetValue(HeaderName, out var provided))
        {
            var providedHash = SHA256.HashData(Encoding.UTF8.GetBytes(provided.ToString()));
            if (CryptographicOperations.FixedTimeEquals(providedHash, _expectedKeyHash))
            {
                await _next(context);
                return;
            }
        }

        context.Response.StatusCode = StatusCodes.Status401Unauthorized;
        await context.Response.WriteAsJsonAsync(new { message = "Неверный или отсутствующий API-ключ." });
    }
}