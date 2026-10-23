using DiscordBot_API.Models;
using Microsoft.EntityFrameworkCore;

namespace DiscordBot_API.Data;

public class AppDbContext : DbContext
{
    public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }

    public DbSet<User> Users => Set<User>();
    public DbSet<ServerConfig> ServerConfigs => Set<ServerConfig>();
    public DbSet<ReactionRole> Reactions => Set<ReactionRole>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        base.OnModelCreating(modelBuilder);

        modelBuilder.Entity<User>(e =>
        {
            e.Property(u => u.GuildId).HasMaxLength(32);
            e.Property(u => u.DiscordId).HasMaxLength(32);
            e.HasIndex(u => new { u.GuildId, u.DiscordId }).IsUnique();
        });

        modelBuilder.Entity<ServerConfig>(e =>
        {
            e.Property(c => c.GuildId).HasMaxLength(32);
            e.Property(c => c.WelcomeChannelId).HasMaxLength(32);
            e.Property(c => c.VerificationRoleId).HasMaxLength(32);
            e.Property(c => c.LogChannelId).HasMaxLength(32);
            e.Property(c => c.TrapChannelId).HasMaxLength(32);
            e.HasIndex(c => c.GuildId).IsUnique();
        });

        modelBuilder.Entity<ReactionRole>(e =>
        {
            e.Property(r => r.GuildId).HasMaxLength(32);
            e.Property(r => r.RoleId).HasMaxLength(32);
            e.Property(r => r.Category).HasMaxLength(64);
            e.Property(r => r.Emoji).HasMaxLength(64);
            e.Property(r => r.Name).HasMaxLength(100);
            e.HasIndex(r => new { r.GuildId, r.RoleId }).IsUnique();
        });
    }
}