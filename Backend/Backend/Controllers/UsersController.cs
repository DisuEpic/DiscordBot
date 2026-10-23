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
        user.IsVerified = true;

        await _context.SaveChangesAsync();
        return Ok(new { message = "Пользователь успешно верифицирован", discordId = user.DiscordId });
    }

    [HttpGet("{guildId}")]
    public async Task<IActionResult> GetGuildUsers(string guildId)
    {
        if (!Snowflake.IsValid(guildId)) return BadRequest(new { message = "Некорректный GuildId." });

        var users = await _context.Users.AsNoTracking().Where(u => u.GuildId == guildId).ToListAsync();
        return Ok(users.Select(u => ToDto(u)));
    }

    [HttpGet("{guildId}/{discordId}")]
    public async Task<IActionResult> GetUser(string guildId, string discordId)
    {
        if (ValidateIds(guildId, discordId) is { } error) return error;

        var user = await _context.Users.AsNoTracking()
            .FirstOrDefaultAsync(u => u.GuildId == guildId && u.DiscordId == discordId);

        return user == null ? NotFound(new { message = "Пользователь не найден." }) : Ok(ToDto(user));
    }

    [HttpPost("{guildId}/{discordId}/roles")]
    public async Task<IActionResult> UpdateUserRole(string guildId, string discordId, [FromBody] UpdateRoleRequest request)
    {
        if (ValidateIds(guildId, discordId) is { } error) return error;
        if (!Snowflake.IsValid(request.RoleId))
            return BadRequest(new { message = "Некорректный RoleId." });

        var user = await EnsureUserExistsAsync(guildId, discordId);

        var roles = user.Roles.ToList();
        if (request.Add)
        {
            if (!roles.Contains(request.RoleId)) roles.Add(request.RoleId);
        }
        else
        {
            roles.Remove(request.RoleId);
        }
        user.Roles = roles;

        await _context.SaveChangesAsync();
        return Ok(new { message = "Роли пользователя обновлены", roles = user.Roles });
    }
}