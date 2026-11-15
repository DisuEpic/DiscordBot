using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DiscordBot_API.Migrations
{
    /// <inheritdoc />
    public partial class AddModularConfigs : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "GuildCoreConfigs",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    GuildId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    LogChannelId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: true),
                    IsPremium = table.Column<bool>(type: "boolean", nullable: false),
                    PremiumUntil = table.Column<DateTime>(type: "timestamp with time zone", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_GuildCoreConfigs", x => x.Id);
                    table.UniqueConstraint("AK_GuildCoreConfigs_GuildId", x => x.GuildId);
                });

            migrationBuilder.CreateTable(
                name: "GuildAiConfigs",
                columns: table => new
                {
                    GuildId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    Enabled = table.Column<bool>(type: "boolean", nullable: false),
                    Mode = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    Provider = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    CustomScenario = table.Column<string>(type: "text", nullable: true),
                    CustomRules = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_GuildAiConfigs", x => x.GuildId);
                    table.ForeignKey(
                        name: "FK_GuildAiConfigs_GuildCoreConfigs_GuildId",
                        column: x => x.GuildId,
                        principalTable: "GuildCoreConfigs",
                        principalColumn: "GuildId",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "GuildSecurityConfigs",
                columns: table => new
                {
                    GuildId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    VerificationRoleId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: true),
                    TrapChannelId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: true),
                    UseCaptcha = table.Column<bool>(type: "boolean", nullable: false),
                    AutoKickUnverified = table.Column<bool>(type: "boolean", nullable: false),
                    VerifyTimeoutMinutes = table.Column<int>(type: "integer", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_GuildSecurityConfigs", x => x.GuildId);
                    table.ForeignKey(
                        name: "FK_GuildSecurityConfigs_GuildCoreConfigs_GuildId",
                        column: x => x.GuildId,
                        principalTable: "GuildCoreConfigs",
                        principalColumn: "GuildId",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "GuildVoiceConfigs",
                columns: table => new
                {
                    GuildId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    GeneratorChannelId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: true),
                    RoomTemplate = table.Column<string>(type: "character varying(64)", maxLength: 64, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_GuildVoiceConfigs", x => x.GuildId);
                    table.ForeignKey(
                        name: "FK_GuildVoiceConfigs_GuildCoreConfigs_GuildId",
                        column: x => x.GuildId,
                        principalTable: "GuildCoreConfigs",
                        principalColumn: "GuildId",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateTable(
                name: "GuildWelcomeConfigs",
                columns: table => new
                {
                    GuildId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    ChannelId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: true),
                    Title = table.Column<string>(type: "text", nullable: true),
                    Description = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_GuildWelcomeConfigs", x => x.GuildId);
                    table.ForeignKey(
                        name: "FK_GuildWelcomeConfigs_GuildCoreConfigs_GuildId",
                        column: x => x.GuildId,
                        principalTable: "GuildCoreConfigs",
                        principalColumn: "GuildId",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_GuildCoreConfigs_GuildId",
                table: "GuildCoreConfigs",
                column: "GuildId",
                unique: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "GuildAiConfigs");

            migrationBuilder.DropTable(
                name: "GuildSecurityConfigs");

            migrationBuilder.DropTable(
                name: "GuildVoiceConfigs");

            migrationBuilder.DropTable(
                name: "GuildWelcomeConfigs");

            migrationBuilder.DropTable(
                name: "GuildCoreConfigs");
        }
    }
}
