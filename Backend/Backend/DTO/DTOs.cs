namespace DiscordBot_API.DTO;

public record VerifyRequest(string GuildId, string DiscordId);
public record UpdateRoleRequest(string RoleId, bool Add);
public record BatchUpdateRolesRequest(List<string>? AddRoleIds, List<string>? RemoveRoleIds);

// --- МОДУЛЬНЫЕ ЗАПРОСЫ НА ОБНОВЛЕНИЕ (PUT) ---

public record UpdateGeneralConfigRequest(
    string? LogChannelId);

public record UpdateSecurityConfigRequest(
    string? VerificationRoleId,
    string? TrapChannelId,
    bool? UseCaptcha = true,
    bool? AutoKickUnverified = false,
    int? VerifyTimeoutMinutes = 10);

public record UpdateWelcomeConfigRequest(
    string? ChannelId,
    string? Title,
    string? Description);

public record UpdateVoiceConfigRequest(
    string? GeneratorChannelId,
    string? RoomTemplate);

public record UpdateAiConfigRequest(
    bool? Enabled = true,
    string? Mode = "standard",
    string? Provider = "auto",
    string? CustomScenario = null,
    string? CustomRules = null);

// --- RESPONSE DTO (ЧТО ОТДАЕТ GET /api/config/{guildId}) ---

public record SecurityConfigDto(
    string? VerificationRoleId,
    string? TrapChannelId,
    bool UseCaptcha,
    bool AutoKickUnverified,
    int VerifyTimeoutMinutes);

public record WelcomeConfigDto(
    string? ChannelId,
    string? Title,
    string? Description);

public record VoiceConfigDto(
    string? GeneratorChannelId,
    string? RoomTemplate);

public record AiConfigDto(
    bool Enabled,
    string Mode,
    string Provider,
    string? CustomScenario,
    string? CustomRules);

public record GuildConfigDto(
    string GuildId,
    string? LogChannelId,
    bool IsPremium,
    DateTime? PremiumUntil,
    SecurityConfigDto Security,
    WelcomeConfigDto Welcome,
    VoiceConfigDto Voice,
    AiConfigDto Ai);

public record ReactionRoleRequest(string GuildId, string Category, string Emoji, string RoleId, string Name);

public record UserDto(string GuildId, string DiscordId, bool IsVerified, DateTime JoinedAt, List<string> Roles);