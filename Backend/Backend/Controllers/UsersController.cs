using DiscordBot_API.Data;
using DiscordBot_API.DTO;
using DiscordBot_API.Helpers;
using DiscordBot_API.Models;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;

namespace DiscordBot_API.Controllers;

[ApiController]
[Route("api/[controller]")]
public class UsersController : ControllerBase
{
    private readonly AppDbContext _context;

    public UsersController(AppDbContext context) => _context = context;

    private static UserDto ToDto(User u) => new(u.GuildId, u.DiscordId, u.IsVerified, u.JoinedAt, u.Roles);

    // Находит профиль участника или безопасно создаёт новый при первом обращении
    private async Task<User> EnsureUserExistsAsync(string guildId, string discordId)
    {
        var user = await _context.Users.FirstOrDefaultAsync(u => u.GuildId == guildId && u.DiscordId == discordId);
        if (user != null)
            return user;

        var newUser = new User { GuildId = guildId, DiscordId = discordId };
        _context.Users.Add(newUser);
        try
        {
            await _context.SaveChangesAsync();
            return newUser;
        }
        catch (DbUpdateException)
        {
            _context.Entry(newUser).State = EntityState.Detached;
            return await _context.Users.FirstAsync(u => u.GuildId == guildId && u.DiscordId == discordId);
        }
    }

    private IActionResult? ValidateIds(string guildId, string discordId) =>
        Snowflake.IsValid(guildId) && Snowflake.IsValid(discordId)
            ? null
            : BadRequest(new { message = "Некорректный GuildId или DiscordId." });

    [HttpPost("verify")]
    public async Task<IActionResult> VerifyUser([FromBody] VerifyRequest request)
    {
        if (ValidateIds(request.GuildId, request.DiscordId) is { } error) return error;

        var user = await EnsureUserExistsAsync(request.GuildId, request.DiscordId);
        if (!user.IsVerified)
        {
            user.IsVerified = true;
            await _context.SaveChangesAsync();
        }

        return Ok(new { message = "Пользователь успешно верифицирован", discordId = user.DiscordId });
    }

    [HttpGet("{guildId}")]
    public async Task<IActionResult> GetGuildUsers(string guildId)
    {
        if (!Snowflake.IsValid(guildId)) return BadRequest(new { message = "Некорректный GuildId." });

        // Проекция Select сразу в SQL без загрузки лишнего столбца Id (Guid) в память
        var users = await _context.Users
            .AsNoTracking()
            .Where(u => u.GuildId == guildId)
            .Select(u => new UserDto(u.GuildId, u.DiscordId, u.IsVerified, u.JoinedAt, u.Roles))
            .ToListAsync();

        return Ok(users);
    }

    [HttpGet("{guildId}/{discordId}")]
    public async Task<IActionResult> GetUser(string guildId, string discordId)
    {
        if (ValidateIds(guildId, discordId) is { } error) return error;

        var userDto = await _context.Users
            .AsNoTracking()
            .Where(u => u.GuildId == guildId && u.DiscordId == discordId)
            .Select(u => new UserDto(u.GuildId, u.DiscordId, u.IsVerified, u.JoinedAt, u.Roles))
            .FirstOrDefaultAsync();

        return userDto == null
            ? NotFound(new { message = "Пользователь не найден." })
            : Ok(userDto);
    }

    [HttpPost("{guildId}/{discordId}/roles")]
    public async Task<IActionResult> UpdateUserRole(string guildId, string discordId, [FromBody] UpdateRoleRequest request)
    {
        if (ValidateIds(guildId, discordId) is { } error) return error;
        if (!Snowflake.IsValid(request.RoleId))
            return BadRequest(new { message = "Некорректный RoleId." });

        var user = await EnsureUserExistsAsync(guildId, discordId);

        var roles = user.Roles.ToList();
        var changed = false;

        if (request.Add)
        {
            if (!roles.Contains(request.RoleId))
            {
                roles.Add(request.RoleId);
                changed = true;
            }
        }
        else
        {
            changed = roles.Remove(request.RoleId);
        }

        // Сохраняем в базу только если список ролей действительно изменился
        if (changed)
        {
            user.Roles = roles;
            await _context.SaveChangesAsync();
        }

        return Ok(new { message = "Роли пользователя обновлены", roles = user.Roles });
    }

    [HttpPost("{guildId}/{discordId}/roles/batch")]
    public async Task<IActionResult> BatchUpdateUserRoles(string guildId, string discordId, [FromBody] BatchUpdateRolesRequest request)
    {
        if (ValidateIds(guildId, discordId) is { } error) return error;

        var toAdd = (request.AddRoleIds ?? new List<string>()).Where(Snowflake.IsValid).ToList();
        var toRemove = (request.RemoveRoleIds ?? new List<string>()).Where(Snowflake.IsValid).ToHashSet();

        var user = await EnsureUserExistsAsync(guildId, discordId);

        var rolesSet = user.Roles.ToHashSet();
        var initialCount = rolesSet.Count;

        rolesSet.ExceptWith(toRemove);
        var afterRemoveCount = rolesSet.Count;

        foreach (var r in toAdd)
            rolesSet.Add(r);

        // Избегаем лишнего UPDATE в БД, если набор ролей остался прежним
        if (afterRemoveCount != initialCount || rolesSet.Count != afterRemoveCount)
        {
            user.Roles = rolesSet.ToList();
            await _context.SaveChangesAsync();
        }

        return Ok(new { message = "Роли пользователя пакетно обновлены", roles = user.Roles });
    }

    [HttpPost("unverify")]
    public async Task<IActionResult> UnverifyUser([FromBody] VerifyRequest request)
    {
        if (ValidateIds(request.GuildId, request.DiscordId) is { } error)
            return error;

        var user = await _context.Users.FirstOrDefaultAsync(u => u.GuildId == request.GuildId && u.DiscordId == request.DiscordId);
        if (user == null)
            return NotFound(new { message = "Пользователь не найден в базе данных" });

        user.IsVerified = false;
        user.Roles = new List<string>();
        await _context.SaveChangesAsync();

        return Ok(new { message = "Верификация пользователя аннулирована, профиль сброшен." });
    }
}