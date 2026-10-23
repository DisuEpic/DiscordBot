using DiscordBot_API.Data;
using DiscordBot_API.DTO;
using DiscordBot_API.Helpers;
using DiscordBot_API.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DiscordBot_API.Controllers;

[ApiController]
[Route("api/[controller]")]
public class ConfigController : ControllerBase
{
    private readonly AppDbContext _context;

    public ConfigController(AppDbContext context) => _context = context;

    [HttpGet("{guildId}")]
    public async Task<IActionResult> GetConfig(string guildId)
    {
        if (!Snowflake.IsValid(guildId))
            return BadRequest(new { message = "Некорректный GuildId." });

        var config = await _context.ServerConfigs.AsNoTracking().FirstOrDefaultAsync(c => c.GuildId == guildId);
        if (config == null)
            return NotFound(new { message = "Настройки для указанного сервера не найдены." });

        return Ok(config);
    }

    [HttpPost]
    public async Task<IActionResult> SaveConfig([FromBody] ConfigRequest request)
    {
        if (!Snowflake.IsValid(request.GuildId))
            return BadRequest(new { message = "GuildId (ID сервера) не может быть пустым или некорректным." });

        if (!Snowflake.TryNormalizeOptional(request.WelcomeChannelId, out var welcomeId) ||
            !Snowflake.TryNormalizeOptional(request.VerificationRoleId, out var verifyRoleId) ||
            !Snowflake.TryNormalizeOptional(request.LogChannelId, out var logId) ||
            !Snowflake.TryNormalizeOptional(request.TrapChannelId, out var trapId))
        {
            return BadRequest(new { message = "Один или несколько указанных ID каналов/ролей имеют некорректный формат Snowflake." });
        }

        var config = await _context.ServerConfigs.FirstOrDefaultAsync(c => c.GuildId == request.GuildId);
        if (config == null)
        {
            config = new ServerConfig { GuildId = request.GuildId };
            _context.ServerConfigs.Add(config);
        }

        config.WelcomeChannelId = welcomeId;
        config.VerificationRoleId = verifyRoleId;
        config.LogChannelId = logId;
        config.TrapChannelId = trapId;

        await _context.SaveChangesAsync();
        return Ok(new { message = "Конфигурация сервера успешно сохранена!" });
    }
}