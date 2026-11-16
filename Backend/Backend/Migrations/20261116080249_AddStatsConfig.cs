using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace DiscordBot_API.Migrations
{
    /// <inheritdoc />
    public partial class AddStatsConfig : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "GuildStatsConfigs",
                columns: table => new
                {
                    GuildId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: false),
                    Enabled = table.Column<bool>(type: "boolean", nullable: false),
                    Style = table.Column<string>(type: "character varying(16)", maxLength: 16, nullable: false),
                    CategoryId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: true),
                    AllMembersChannelId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: true),
                    MembersChannelId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: true),
                    BotsChannelId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: true),
                    ChannelsChannelId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: true),
                    RolesChannelId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: true),
                    VoiceChannelId = table.Column<string>(type: "character varying(32)", maxLength: 32, nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_GuildStatsConfigs", x => x.GuildId);
                    table.ForeignKey(
                        name: "FK_GuildStatsConfigs_GuildCoreConfigs_GuildId",
                        column: x => x.GuildId,
                        principalTable: "GuildCoreConfigs",
                        principalColumn: "GuildId",
                        onDelete: ReferentialAction.Cascade);
                });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "GuildStatsConfigs");
        }
    }
}
