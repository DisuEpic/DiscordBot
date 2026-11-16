using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DiscordBot_API.Migrations
{
    /// <inheritdoc />
    public partial class DropOldServerConfigs : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "ServerConfigs");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "ServerConfigs",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    AiCustomRules = table.Column<string>(type: "text", nullable: true),
                    AiCustomScenario = table.Column<string>(type: "text", nullable: true),
                    AiEnabled = table.Column<bool>(type: "boolean", nullable: false),
                    AiMode = table.Column<string>(type: "text", nullable: true),
                    AiProvider = table.Column<string>(type: "text", nullable: true),
                    GuildId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    LogChannelId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: true),
                    TrapChannelId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: true),
                    VerificationRoleId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: true),
                    VoiceGeneratorChannelId = table.Column<string>(type: "text", nullable: true),
                    VoiceRoomTemplate = table.Column<string>(type: "text", nullable: true),
                    WelcomeChannelId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: true),
                    WelcomeDescription = table.Column<string>(type: "text", nullable: true),
                    WelcomeTitle = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ServerConfigs", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_ServerConfigs_GuildId",
                table: "ServerConfigs",
                column: "GuildId",
                unique: true);
        }
    }
}
