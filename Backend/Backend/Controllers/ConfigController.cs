using DiscordBot_API.Data;
using DiscordBot_API.DTO;
using DiscordBot_API.Helpers;
using DiscordBot_API.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Caching.Memory;
using System.Text.Json;
namespace DiscordBot_API.Controllers;

[ApiController]
[Route("api/[controller]")]
public class ConfigController : ControllerBase
{
    private readonly AppDbContext _context;
    private readonly IMemoryCache _cache;

    // Настраиваемый параметр: время жизни кэша настроек в ОЗУ
    private static readonly TimeSpan CacheDuration = TimeSpan.FromMinutes(5);

    public ConfigController(AppDbContext context, IMemoryCache cache)
    {
        _context = context;
        _cache = cache;
    }

    private static string GetCacheKey(string guildId) => $"guild_config:{guildId}";

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
            c.Security?.VerifyTimeoutMinutes ?? 10,
            GetAutomodConfig(c.Security)
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
            c.Ai?.Provider ?? "auto",
            c.Ai?.AutoReplyChance ?? 0,
            c.Ai?.CustomScenario,
            c.Ai?.CustomRules
        ),
        new StatsConfigDto(
            c.Stats?.Enabled ?? false,
            c.Stats?.Style ?? "en",
            c.Stats?.CategoryId,
            c.Stats?.AllMembersChannelId,
            c.Stats?.MembersChannelId,
            c.Stats?.BotsChannelId,
            c.Stats?.ChannelsChannelId,
            c.Stats?.RolesChannelId,
            c.Stats?.VoiceChannelId
        )
    );

    private IQueryable<GuildCoreConfig> QueryFullConfig() =>
        _context.GuildCoreConfigs
            .Include(c => c.Security)
            .Include(c => c.Welcome)
            .Include(c => c.Voice)
            .Include(c => c.Ai)
            .Include(c => c.Stats);

    private async Task<GuildCoreConfig> EnsureCoreConfigExistsAsync(string guildId)
    {
        var core = await QueryFullConfig().FirstOrDefaultAsync(c => c.GuildId == guildId);

        if (core != null)
        {
            var changed = false;
            if (core.Security == null) { core.Security = new GuildSecurityConfig { GuildId = guildId }; changed = true; }
            if (core.Welcome == null) { core.Welcome = new GuildWelcomeConfig { GuildId = guildId }; changed = true; }
            if (core.Voice == null) { core.Voice = new GuildVoiceConfig { GuildId = guildId }; changed = true; }
            if (core.Ai == null) { core.Ai = new GuildAiConfig { GuildId = guildId }; changed = true; }
            if (core.Stats == null) { core.Stats = new GuildStatsConfig { GuildId = guildId }; changed = true; }

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
            Ai = new GuildAiConfig { GuildId = guildId },
            Stats = new GuildStatsConfig { GuildId = guildId }
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
            return await QueryFullConfig().FirstAsync(c => c.GuildId == guildId);
        }
    }

    private OkObjectResult SaveCacheAndReturnOk(GuildCoreConfig core)
    {
        var dto = ToDto(core);
        _cache.Set(GetCacheKey(core.GuildId), dto, CacheDuration);
        return Ok(dto);
    }

    [HttpGet("{guildId}")]
    public async Task<IActionResult> GetConfig(string guildId)
    {
        if (!Snowflake.IsValid(guildId))
            return BadRequest(new { message = "Некорректный GuildId." });

        var cacheKey = GetCacheKey(guildId);
        if (_cache.TryGetValue(cacheKey, out GuildConfigDto? cachedDto) && cachedDto != null)
            return Ok(cachedDto);

        var config = await QueryFullConfig()
            .AsNoTracking()
            .FirstOrDefaultAsync(c => c.GuildId == guildId);

        if (config == null)
            return NotFound(new { message = "Настройки для указанного сервера не найдены." });

        var dto = ToDto(config);
        _cache.Set(cacheKey, dto, CacheDuration);

        return Ok(dto);
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
        return SaveCacheAndReturnOk(core);
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
        return SaveCacheAndReturnOk(core);
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
        return SaveCacheAndReturnOk(core);
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
        return SaveCacheAndReturnOk(core);
    }

    [HttpPut("{guildId}/ai")]
    public async Task<IActionResult> UpdateAi(string guildId, [FromBody] UpdateAiConfigRequest request)
    {
        if (!Snowflake.IsValid(guildId))
            return BadRequest(new { message = "Некорректный GuildId." });

        var core = await EnsureCoreConfigExistsAsync(guildId);
        var ai = core.Ai!;

        var provider = NormalizeOptionalText(request.Provider)?.ToLowerInvariant() ?? "auto";
        if (provider.Length > 32)
            provider = provider[..32];

        ai.Enabled = request.Enabled ?? true;
        ai.Provider = provider;
        ai.AutoReplyChance = Math.Clamp(request.AutoReplyChance ?? 0, 0, 100);
        ai.CustomScenario = NormalizeOptionalText(request.CustomScenario);
        ai.CustomRules = NormalizeOptionalText(request.CustomRules);

        await _context.SaveChangesAsync();
        return SaveCacheAndReturnOk(core);
    }

    [HttpPut("{guildId}/stats")]
    public async Task<IActionResult> UpdateStats(string guildId, [FromBody] UpdateStatsConfigRequest request)
    {
        if (!Snowflake.IsValid(guildId))
            return BadRequest(new { message = "Некорректный GuildId." });

        if (!Snowflake.TryNormalizeOptional(request.CategoryId, out var categoryId) ||
            !Snowflake.TryNormalizeOptional(request.AllMembersChannelId, out var allMembersId) ||
            !Snowflake.TryNormalizeOptional(request.MembersChannelId, out var membersId) ||
            !Snowflake.TryNormalizeOptional(request.BotsChannelId, out var botsId) ||
            !Snowflake.TryNormalizeOptional(request.ChannelsChannelId, out var channelsId) ||
            !Snowflake.TryNormalizeOptional(request.RolesChannelId, out var rolesId) ||
            !Snowflake.TryNormalizeOptional(request.VoiceChannelId, out var voiceId))
        {
            return BadRequest(new { message = "Один или несколько ID каналов/категории статистики имеют некорректный формат Snowflake." });
        }

        var core = await EnsureCoreConfigExistsAsync(guildId);
        var stats = core.Stats!;

        var style = NormalizeOptionalText(request.Style)?.ToLowerInvariant() ?? "en";
        if (style is not ("en" or "ru"))
            style = "en";

        stats.Enabled = request.Enabled ?? false;
        stats.Style = style;
        stats.CategoryId = categoryId;
        stats.AllMembersChannelId = allMembersId;
        stats.MembersChannelId = membersId;
        stats.BotsChannelId = botsId;
        stats.ChannelsChannelId = channelsId;
        stats.RolesChannelId = rolesId;
        stats.VoiceChannelId = voiceId;

        await _context.SaveChangesAsync();
        return SaveCacheAndReturnOk(core);
    }
    private static AutomodScopeDto? ReadAutomodScope(string? value) =>
    value is null ? null : JsonSerializer.Deserialize<AutomodScopeDto>(value);

    private static AutomodConfigDto GetAutomodConfig(GuildSecurityConfig? security) =>
        new(
            security?.AutomodInvites,
            security?.AutomodSpam,
            security?.AutomodMentions,
            new Dictionary<string, AutomodScopeDto?>
            {
                ["invites"] = ReadAutomodScope(security?.AutomodInvitesScope),
                ["spam"] = ReadAutomodScope(security?.AutomodSpamScope),
                ["mentions"] = ReadAutomodScope(security?.AutomodMentionsScope)
            });

    [HttpPut("{guildId}/security/automod/{filter}")]
    public async Task<IActionResult> UpdateAutomodFilter(
        string guildId,
        string filter,
        [FromBody] UpdateAutomodFilterRequest request)
    {
        if (!Snowflake.IsValid(guildId))
            return BadRequest(new { message = "Некорректный GuildId." });

        if (filter is not ("invites" or "spam" or "mentions") ||
            request.Enabled is not bool enabled)
        {
            return BadRequest(new { message = "Укажи фильтр и значение enabled." });
        }

        string? serializedScope = null;

        if (request.Scope is { } scope)
        {
            var ids = scope.ChannelIds;
            if (ids is null || ids.Any(id => !Snowflake.IsValid(id)))
                return BadRequest(new { message = "Некорректный ID канала." });

            var channelIds = ids.Distinct().ToArray();
            var validScope = scope.Mode switch
            {
                "all" => channelIds.Length == 0,
                "exclude" => channelIds.Length is >= 1 and <= 50,
                "only" => channelIds.Length == 1,
                _ => false
            };

            if (!validScope)
                return BadRequest(new { message = "Некорректная область AutoMod." });

            serializedScope = JsonSerializer.Serialize(
                new AutomodScopeDto(scope.Mode, channelIds));
        }

        var core = await EnsureCoreConfigExistsAsync(guildId);
        var security = core.Security!;

        switch (filter)
        {
            case "invites":
                security.AutomodInvites = enabled;
                if (serializedScope is not null)
                    security.AutomodInvitesScope = serializedScope;
                break;

            case "spam":
                security.AutomodSpam = enabled;
                if (serializedScope is not null)
                    security.AutomodSpamScope = serializedScope;
                break;

            case "mentions":
                security.AutomodMentions = enabled;
                if (serializedScope is not null)
                    security.AutomodMentionsScope = serializedScope;
                break;
        }

        await _context.SaveChangesAsync();
        return SaveCacheAndReturnOk(core);
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
        core.Ai.Provider = "auto";
        core.Ai.AutoReplyChance = 0;
        core.Ai.CustomScenario = null;
        core.Ai.CustomRules = null;

        core.Stats!.Enabled = false;
        core.Stats.Style = "en";
        core.Stats.CategoryId = null;
        core.Stats.AllMembersChannelId = null;
        core.Stats.MembersChannelId = null;
        core.Stats.BotsChannelId = null;
        core.Stats.ChannelsChannelId = null;
        core.Stats.RolesChannelId = null;
        core.Stats.VoiceChannelId = null;

        await _context.SaveChangesAsync();
        return SaveCacheAndReturnOk(core);
    }
}