using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DiscordBot_API.Migrations
{
    /// <inheritdoc />
    public partial class AddVoiceRoomTemplate : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "VoiceGeneratorChannelId",
                table: "ServerConfigs",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "VoiceRoomTemplate",
                table: "ServerConfigs",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "WelcomeDescription",
                table: "ServerConfigs",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "WelcomeTitle",
                table: "ServerConfigs",
                type: "text",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "VoiceGeneratorChannelId",
                table: "ServerConfigs");

            migrationBuilder.DropColumn(
                name: "VoiceRoomTemplate",
                table: "ServerConfigs");

            migrationBuilder.DropColumn(
                name: "WelcomeDescription",
                table: "ServerConfigs");

            migrationBuilder.DropColumn(
                name: "WelcomeTitle",
                table: "ServerConfigs");
        }
    }
}
