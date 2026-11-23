using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DiscordBot_API.Migrations
{
    /// <inheritdoc />
    public partial class AutoModeration : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<bool>(
                name: "AutomodInvites",
                table: "GuildSecurityConfigs",
                type: "boolean",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "AutomodInvitesScope",
                table: "GuildSecurityConfigs",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<bool>(
                name: "AutomodMentions",
                table: "GuildSecurityConfigs",
                type: "boolean",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "AutomodMentionsScope",
                table: "GuildSecurityConfigs",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<bool>(
                name: "AutomodSpam",
                table: "GuildSecurityConfigs",
                type: "boolean",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "AutomodSpamScope",
                table: "GuildSecurityConfigs",
                type: "text",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "AutomodInvites",
                table: "GuildSecurityConfigs");

            migrationBuilder.DropColumn(
                name: "AutomodInvitesScope",
                table: "GuildSecurityConfigs");

            migrationBuilder.DropColumn(
                name: "AutomodMentions",
                table: "GuildSecurityConfigs");

            migrationBuilder.DropColumn(
                name: "AutomodMentionsScope",
                table: "GuildSecurityConfigs");

            migrationBuilder.DropColumn(
                name: "AutomodSpam",
                table: "GuildSecurityConfigs");

            migrationBuilder.DropColumn(
                name: "AutomodSpamScope",
                table: "GuildSecurityConfigs");
        }
    }
}
