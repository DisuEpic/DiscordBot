namespace DiscordBot_API.DTO;

public record VerifyRequest(string GuildId, string DiscordId);
public record UpdateRoleRequest(string RoleId, bool Add);
public record BatchUpdateRolesRequest(List<string>? AddRoleIds, List<string>? RemoveRoleIds);

public record ConfigRequest(
    string GuildId,
    string? WelcomeChannelId,
    string? VerificationRoleId,
    string? LogChannelId,
    string? TrapChannelId);

public record ReactionRoleRequest(string GuildId, string Category, string Emoji, string RoleId, string Name);

public record UserDto(string GuildId, string DiscordId, bool IsVerified, DateTime JoinedAt, List<string> Roles);