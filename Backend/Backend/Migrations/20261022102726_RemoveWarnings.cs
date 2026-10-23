using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DiscordBot_API.Migrations
{
    /// <inheritdoc />
    public partial class RemoveWarnings : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "Warnings");
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "Warnings",
                columns: table => new
                {
                    Id = table.Column<Guid>(type: "uuid", nullable: false),
                    CreatedAt = table.Column<DateTime>(type: "timestamp with time zone", nullable: false),
                    DiscordId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    GuildId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    ModeratorId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    ModeratorName = table.Column<string>(type: "character varying(100)", maxLength: 100, nullable: false),
                    Reason = table.Column<string>(type: "character varying(500)", maxLength: 500, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Warnings", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_Warnings_GuildId_DiscordId",
                table: "Warnings",
                columns: new[] { "GuildId", "DiscordId" });
        }
    }
}
