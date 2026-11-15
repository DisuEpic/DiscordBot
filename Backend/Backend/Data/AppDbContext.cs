using DiscordBot_API.Models;
using Microsoft.EntityFrameworkCore;

namespace DiscordBot_API.Data;

public class AppDbContext : DbContext
{
    public AppDbContext(DbContextOptions<AppDbContext> options) : base(options) { }

    public DbSet<User> Users => Set<User>();
    public DbSet<ServerConfig> ServerConfigs => Set<ServerConfig>(); // временно оставляем
    public DbSet<ReactionRole> Reactions => Set<ReactionRole>();

    public DbSet<GuildCoreConfig> GuildCoreConfigs => Set<GuildCoreConfig>();
    public DbSet<GuildSecurityConfig> GuildSecurityConfigs => Set<GuildSecurityConfig>();
    public DbSet<GuildWelcomeConfig> GuildWelcomeConfigs => Set<GuildWelcomeConfig>();
    public DbSet<GuildVoiceConfig> GuildVoiceConfigs => Set<GuildVoiceConfig>();
    public DbSet<GuildAiConfig> GuildAiConfigs => Set<GuildAiConfig>();

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

        modelBuilder.Entity<GuildCoreConfig>(e =>
        {
            e.Property(c => c.GuildId).HasMaxLength(32);
            e.Property(c => c.LogChannelId).HasMaxLength(32);
            e.HasIndex(c => c.GuildId).IsUnique();

            e.HasOne(c => c.Security)
                .WithOne()
                .HasForeignKey<GuildSecurityConfig>(s => s.GuildId)
                .HasPrincipalKey<GuildCoreConfig>(c => c.GuildId)
                .OnDelete(DeleteBehavior.Cascade);

            e.HasOne(c => c.Welcome)
                .WithOne()
                .HasForeignKey<GuildWelcomeConfig>(w => w.GuildId)
                .HasPrincipalKey<GuildCoreConfig>(c => c.GuildId)
                .OnDelete(DeleteBehavior.Cascade);

            e.HasOne(c => c.Voice)
                .WithOne()
                .HasForeignKey<GuildVoiceConfig>(v => v.GuildId)
                .HasPrincipalKey<GuildCoreConfig>(c => c.GuildId)
                .OnDelete(DeleteBehavior.Cascade);

            e.HasOne(c => c.Ai)
                .WithOne()
                .HasForeignKey<GuildAiConfig>(a => a.GuildId)
                .HasPrincipalKey<GuildCoreConfig>(c => c.GuildId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<GuildSecurityConfig>(e =>
        {
            e.HasKey(s => s.GuildId);
            e.Property(s => s.GuildId).HasMaxLength(32);
            e.Property(s => s.VerificationRoleId).HasMaxLength(32);
            e.Property(s => s.TrapChannelId).HasMaxLength(32);
        });

        modelBuilder.Entity<GuildWelcomeConfig>(e =>
        {
            e.HasKey(w => w.GuildId);
            e.Property(w => w.GuildId).HasMaxLength(32);
            e.Property(w => w.ChannelId).HasMaxLength(32);
        });

        modelBuilder.Entity<GuildVoiceConfig>(e =>
        {
            e.HasKey(v => v.GuildId);
            e.Property(v => v.GuildId).HasMaxLength(32);
            e.Property(v => v.GeneratorChannelId).HasMaxLength(32);
            e.Property(v => v.RoomTemplate).HasMaxLength(64);
        });

        modelBuilder.Entity<GuildAiConfig>(e =>
        {
            e.HasKey(a => a.GuildId);
            e.Property(a => a.GuildId).HasMaxLength(32);
            e.Property(a => a.Mode).HasMaxLength(32);
            e.Property(a => a.Provider).HasMaxLength(32);
        });
    }
}