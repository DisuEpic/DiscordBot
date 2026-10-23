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