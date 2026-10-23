using DiscordBot_API.Data;
using DiscordBot_API.DTO;
using DiscordBot_API.Helpers;
using DiscordBot_API.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DiscordBot_API.Controllers;

[ApiController]
[Route("api/[controller]")]
public class RolesController : ControllerBase
{
    private const int MaxRolesPerCategory = 25;
    private readonly AppDbContext _context;

    public RolesController(AppDbContext context) => _context = context;

    private static string TrimToMax(string? value, int maxLength)
    {
        var trimmed = (value ?? string.Empty).Trim();
        return trimmed.Length <= maxLength ? trimmed : trimmed[..maxLength];
    }

    [HttpGet]
    public async Task<IActionResult> GetRoles([FromQuery] string guildId)
    {
        if (!Snowflake.IsValid(guildId))
            return BadRequest(new { message = "Некорректный guildId." });

        var roles = await _context.Reactions
            .AsNoTracking()
            .Where(r => r.GuildId == guildId)
            .OrderBy(r => r.Category)
            .ThenBy(r => r.Name)
            .ToListAsync();

        return Ok(roles);
    }

    [HttpPost]
    public async Task<IActionResult> AddRole([FromBody] ReactionRoleRequest request)
    {
        if (!Snowflake.IsValid(request.GuildId) || !Snowflake.IsValid(request.RoleId))
            return BadRequest(new { message = "Некорректный GuildId или RoleId." });
        if (string.IsNullOrWhiteSpace(request.Name) || string.IsNullOrWhiteSpace(request.Emoji))
            return BadRequest(new { message = "Name и Emoji не могут быть пустыми." });

        var category = string.IsNullOrWhiteSpace(request.Category) ? "Общие" : TrimToMax(request.Category, 64);
        var emoji = TrimToMax(request.Emoji, 64);
        var name = TrimToMax(request.Name, 100);

        var role = await _context.Reactions
            .FirstOrDefaultAsync(r => r.GuildId == request.GuildId && r.RoleId == request.RoleId);

        var countInCategory = await _context.Reactions.CountAsync(r =>
            r.GuildId == request.GuildId
            && r.RoleId != request.RoleId
            && EF.Functions.ILike(r.Category, category));

        if (countInCategory >= MaxRolesPerCategory)
            return BadRequest(new { message = $"Превышен лимит ролей в категории «{category}» (максимум {MaxRolesPerCategory})." });

        if (role == null)
        {
            role = new ReactionRole
            {
                GuildId = request.GuildId,
                RoleId = request.RoleId,
                Category = category,
                Emoji = emoji,
                Name = name
            };
            _context.Reactions.Add(role);
        }
        else
        {
            role.Category = category;
            role.Emoji = emoji;
            role.Name = name;
        }

        await _context.SaveChangesAsync();
        return Ok(role);
    }

    [HttpDelete("{guildId}/{roleId}")]
    public async Task<IActionResult> DeleteRole(string guildId, string roleId)
    {
        if (!Snowflake.IsValid(guildId) || !Snowflake.IsValid(roleId))
            return BadRequest(new { message = "Некорректный GuildId или RoleId." });

        var role = await _context.Reactions.FirstOrDefaultAsync(r => r.GuildId == guildId && r.RoleId == roleId);
        if (role == null)
            return NotFound(new { message = "Роль не найдена" });

        _context.Reactions.Remove(role);
        await _context.SaveChangesAsync();
        return Ok(new { message = "Роль успешно удалена из базы" });
    }

    [HttpDelete("category/{guildId}/{category}")]
    public async Task<IActionResult> DeleteCategory(string guildId, string category)
    {
        if (!Snowflake.IsValid(guildId))
            return BadRequest(new { message = "Некорректный GuildId." });
        if (string.IsNullOrWhiteSpace(category))
            return BadRequest(new { message = "Категория не может быть пустой." });

        var trimmedCategory = category.Trim();
        var items = await _context.Reactions
            .Where(r => r.GuildId == guildId && EF.Functions.ILike(r.Category, trimmedCategory))
            .ToListAsync();

        if (items.Count == 0)
            return NotFound(new { message = "В этой категории нет ролей" });

        _context.Reactions.RemoveRange(items);
        await _context.SaveChangesAsync();
        return Ok(new { message = "Категория очищена", deleted = items.Count });
    }
}