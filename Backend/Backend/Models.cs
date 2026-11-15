using System.ComponentModel.DataAnnotations.Schema;

namespace DiscordBot_API.Models;

public class User
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public required string GuildId { get; set; }
    public required string DiscordId { get; set; }
    public bool IsVerified { get; set; } = false;
    public DateTime JoinedAt { get; set; } = DateTime.UtcNow;
    public List<string> Roles { get; set; } = new();   // ID ролей
}

public class ServerConfig
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public required string GuildId { get; set; }
    public string? WelcomeChannelId { get; set; }
    public string? VerificationRoleId { get; set; }
    public string? LogChannelId { get; set; }
    public string? TrapChannelId { get; set; }
    public string? WelcomeTitle { get; set; }
    public string? WelcomeDescription { get; set; }
    public string? VoiceGeneratorChannelId { get; set; }
    public string? VoiceRoomTemplate { get; set; }
    public bool AiEnabled { get; set; } = true;
    public string? AiMode { get; set; }
    public string? AiCustomScenario { get; set; }
    public string? AiCustomRules { get; set; }
    public string? AiProvider { get; set; } = "auto";
}

// --- НОВЫЕ МОДУЛЬНЫЕ МОДЕЛИ ---

public class GuildCoreConfig
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public required string GuildId { get; set; }
    public string? LogChannelId { get; set; }
    public bool IsPremium { get; set; } = false;
    public DateTime? PremiumUntil { get; set; }

    public GuildSecurityConfig? Security { get; set; }
    public GuildWelcomeConfig? Welcome { get; set; }
    public GuildVoiceConfig? Voice { get; set; }
    public GuildAiConfig? Ai { get; set; }
}

public class GuildSecurityConfig
{
    public required string GuildId { get; set; }
    public string? VerificationRoleId { get; set; }
    public string? TrapChannelId { get; set; }
    public bool UseCaptcha { get; set; } = true;
    public bool AutoKickUnverified { get; set; } = false;
    public int VerifyTimeoutMinutes { get; set; } = 10;
}

public class GuildWelcomeConfig
{
    public required string GuildId { get; set; }
    public string? ChannelId { get; set; }
    public string? Title { get; set; }
    public string? Description { get; set; }
}

public class GuildVoiceConfig
{
    public required string GuildId { get; set; }
    public string? GeneratorChannelId { get; set; }
    public string? RoomTemplate { get; set; }
}

public class GuildAiConfig
{
    public required string GuildId { get; set; }
    public bool Enabled { get; set; } = true;
    public string Mode { get; set; } = "standard";
    public string Provider { get; set; } = "auto";
    public string? CustomScenario { get; set; }
    public string? CustomRules { get; set; }
}

[Table("Reactions")]
public class ReactionRole
{
    public Guid Id { get; set; } = Guid.NewGuid();
    public required string GuildId { get; set; }
    public string Category { get; set; } = "Общие";
    public required string Emoji { get; set; }
    public required string RoleId { get; set; }
    public required string Name { get; set; }
}