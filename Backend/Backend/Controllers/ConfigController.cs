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

    private static string? NormalizeOptionalText(string? value)
    {
        var trimmed = value?.Trim();
        return string.IsNullOrEmpty(trimmed) ? null : trimmed;
    }

    private static GuildConfigDto ToDto(GuildCoreConfig c) => new(
        c.GuildId,
        c.LogChannelId,
        c.IsPremium,
        c.PremiumUntil,
        new SecurityConfigDto(
            c.Security?.VerificationRoleId,
            c.Security?.TrapChannelId,
            c.Security?.UseCaptcha ?? true,
            c.Security?.AutoKickUnverified ?? false,
            c.Security?.VerifyTimeoutMinutes ?? 10
        ),
        new WelcomeConfigDto(
            c.Welcome?.ChannelId,
            c.Welcome?.Title,
            c.Welcome?.Description
        ),
        new VoiceConfigDto(
            c.Voice?.GeneratorChannelId,
            c.Voice?.RoomTemplate
        ),
        new AiConfigDto(
            c.Ai?.Enabled ?? true,
            c.Ai?.Mode ?? "standard",
            c.Ai?.Provider ?? "auto",
            c.Ai?.CustomScenario,
            c.Ai?.CustomRules
        )
    );

    private async Task<GuildCoreConfig> EnsureCoreConfigExistsAsync(string guildId)
    {
        var core = await _context.GuildCoreConfigs
            .AsSplitQuery()
            .Include(c => c.Security)
            .Include(c => c.Welcome)
            .Include(c => c.Voice)
            .Include(c => c.Ai)
            .FirstOrDefaultAsync(c => c.GuildId == guildId);

        if (core != null)
        {
            var changed = false;
            if (core.Security == null) { core.Security = new GuildSecurityConfig { GuildId = guildId }; changed = true; }
            if (core.Welcome == null) { core.Welcome = new GuildWelcomeConfig { GuildId = guildId }; changed = true; }
            if (core.Voice == null) { core.Voice = new GuildVoiceConfig { GuildId = guildId }; changed = true; }
            if (core.Ai == null) { core.Ai = new GuildAiConfig { GuildId = guildId }; changed = true; }

            if (changed)
                await _context.SaveChangesAsync();

            return core;
        }

        var newCore = new GuildCoreConfig
        {
            GuildId = guildId,
            Security = new GuildSecurityConfig { GuildId = guildId },
            Welcome = new GuildWelcomeConfig { GuildId = guildId },
            Voice = new GuildVoiceConfig { GuildId = guildId },
            Ai = new GuildAiConfig { GuildId = guildId }
        };

        _context.GuildCoreConfigs.Add(newCore);
        try
        {
            await _context.SaveChangesAsync();
            return newCore;
        }
        catch (DbUpdateException)
        {
            _context.ChangeTracker.Clear();
            return await _context.GuildCoreConfigs
                .AsSplitQuery()
                .Include(c => c.Security)
                .Include(c => c.Welcome)
                .Include(c => c.Voice)
                .Include(c => c.Ai)
                .FirstAsync(c => c.GuildId == guildId);
        }
    }

    [HttpGet("{guildId}")]
    public async Task<IActionResult> GetConfig(string guildId)
    {
        if (!Snowflake.IsValid(guildId))
            return BadRequest(new { message = "Некорректный GuildId." });

        var config = await _context.GuildCoreConfigs
            .AsNoTracking()
            .AsSplitQuery()
            .Include(c => c.Security)
            .Include(c => c.Welcome)
            .Include(c => c.Voice)
            .Include(c => c.Ai)
            .FirstOrDefaultAsync(c => c.GuildId == guildId);

        if (config == null)
            return NotFound(new { message = "Настройки для указанного сервера не найдены." });

        return Ok(ToDto(config));
    }

    [HttpPut("{guildId}/general")]
    public async Task<IActionResult> UpdateGeneral(string guildId, [FromBody] UpdateGeneralConfigRequest request)
    {
        if (!Snowflake.IsValid(guildId))
            return BadRequest(new { message = "Некорректный GuildId." });

        if (!Snowflake.TryNormalizeOptional(request.LogChannelId, out var logId))
            return BadRequest(new { message = "Некорректный формат LogChannelId." });

        var core = await EnsureCoreConfigExistsAsync(guildId);
        core.LogChannelId = logId;

        await _context.SaveChangesAsync();
        return Ok(ToDto(core));
    }

    [HttpPut("{guildId}/security")]
    public async Task<IActionResult> UpdateSecurity(string guildId, [FromBody] UpdateSecurityConfigRequest request)
    {
        if (!Snowflake.IsValid(guildId))
            return BadRequest(new { message = "Некорректный GuildId." });

        if (!Snowflake.TryNormalizeOptional(request.VerificationRoleId, out var verifyRoleId) ||
            !Snowflake.TryNormalizeOptional(request.TrapChannelId, out var trapId))
            return BadRequest(new { message = "Некорректный формат ID роли или канала-ловушки." });

        var core = await EnsureCoreConfigExistsAsync(guildId);
        var sec = core.Security!;

        sec.VerificationRoleId = verifyRoleId;
        sec.TrapChannelId = trapId;
        sec.UseCaptcha = request.UseCaptcha ?? true;
        sec.AutoKickUnverified = request.AutoKickUnverified ?? false;
        sec.VerifyTimeoutMinutes = Math.Clamp(request.VerifyTimeoutMinutes ?? 10, 1, 1440);

        await _context.SaveChangesAsync();
        return Ok(ToDto(core));
    }

    [HttpPut("{guildId}/welcome")]
    public async Task<IActionResult> UpdateWelcome(string guildId, [FromBody] UpdateWelcomeConfigRequest request)
    {
        if (!Snowflake.IsValid(guildId))
            return BadRequest(new { message = "Некорректный GuildId." });

        if (!Snowflake.TryNormalizeOptional(request.ChannelId, out var channelId))
            return BadRequest(new { message = "Некорректный формат ChannelId." });

        var core = await EnsureCoreConfigExistsAsync(guildId);
        var welcome = core.Welcome!;

        welcome.ChannelId = channelId;
        welcome.Title = NormalizeOptionalText(request.Title);
        welcome.Description = NormalizeOptionalText(request.Description);

        await _context.SaveChangesAsync();
        return Ok(ToDto(core));
    }

    [HttpPut("{guildId}/voice")]
    public async Task<IActionResult> UpdateVoice(string guildId, [FromBody] UpdateVoiceConfigRequest request)
    {
        if (!Snowflake.IsValid(guildId))
            return BadRequest(new { message = "Некорректный GuildId." });

        if (!Snowflake.TryNormalizeOptional(request.GeneratorChannelId, out var generatorId))
            return BadRequest(new { message = "Некорректный формат GeneratorChannelId." });

        var core = await EnsureCoreConfigExistsAsync(guildId);
        var voice = core.Voice!;

        voice.GeneratorChannelId = generatorId;
        var tpl = NormalizeOptionalText(request.RoomTemplate);
        voice.RoomTemplate = tpl != null && tpl.Length > 64 ? tpl[..64] : tpl;

        await _context.SaveChangesAsync();
        return Ok(ToDto(core));
    }

    [HttpPut("{guildId}/ai")]
    public async Task<IActionResult> UpdateAi(string guildId, [FromBody] UpdateAiConfigRequest request)
    {
        if (!Snowflake.IsValid(guildId))
            return BadRequest(new { message = "Некорректный GuildId." });

        var core = await EnsureCoreConfigExistsAsync(guildId);
        var ai = core.Ai!;

        var mode = NormalizeOptionalText(request.Mode)?.ToLowerInvariant() ?? "standard";
        if (mode is not ("standard" or "overdrive"))
            mode = "standard";

        var provider = NormalizeOptionalText(request.Provider)?.ToLowerInvariant() ?? "auto";
        if (provider.Length > 32)
            provider = provider[..32];

        ai.Enabled = request.Enabled ?? true;
        ai.Mode = mode;
        ai.Provider = provider;
        ai.CustomScenario = NormalizeOptionalText(request.CustomScenario);
        ai.CustomRules = NormalizeOptionalText(request.CustomRules);

        await _context.SaveChangesAsync();
        return Ok(ToDto(core));
    }

    [HttpPost("{guildId}/reset")]
    public async Task<IActionResult> ResetConfig(string guildId)
    {
        if (!Snowflake.IsValid(guildId))
            return BadRequest(new { message = "Некорректный GuildId." });

        var core = await EnsureCoreConfigExistsAsync(guildId);

        core.LogChannelId = null;

        core.Security!.VerificationRoleId = null;
        core.Security.TrapChannelId = null;
        core.Security.UseCaptcha = true;
        core.Security.AutoKickUnverified = false;
        core.Security.VerifyTimeoutMinutes = 10;

        core.Welcome!.ChannelId = null;
        core.Welcome.Title = null;
        core.Welcome.Description = null;

        core.Voice!.GeneratorChannelId = null;
        core.Voice.RoomTemplate = null;

        core.Ai!.Enabled = true;
        core.Ai.Mode = "standard";
        core.Ai.Provider = "auto";
        core.Ai.CustomScenario = null;
        core.Ai.CustomRules = null;

        await _context.SaveChangesAsync();
        return Ok(ToDto(core));
    }
}