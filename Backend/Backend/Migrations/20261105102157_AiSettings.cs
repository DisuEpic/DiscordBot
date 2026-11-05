using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DiscordBot_API.Migrations
{
    /// <inheritdoc />
    public partial class AiSettings : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<string>(
                name: "AiCustomRules",
                table: "ServerConfigs",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "AiCustomScenario",
                table: "ServerConfigs",
                type: "text",
                nullable: true);

            migrationBuilder.AddColumn<bool>(
                name: "AiEnabled",
                table: "ServerConfigs",
                type: "boolean",
                nullable: false,
                defaultValue: false);

            migrationBuilder.AddColumn<string>(
                name: "AiMode",
                table: "ServerConfigs",
                type: "text",
                nullable: true);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropColumn(
                name: "AiCustomRules",
                table: "ServerConfigs");

            migrationBuilder.DropColumn(
                name: "AiCustomScenario",
                table: "ServerConfigs");

            migrationBuilder.DropColumn(
                name: "AiEnabled",
                table: "ServerConfigs");

            migrationBuilder.DropColumn(
                name: "AiMode",
                table: "ServerConfigs");
        }
    }
}
