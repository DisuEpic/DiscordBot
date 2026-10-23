namespace DiscordBot_API.Helpers;

public static class Snowflake
{
    public static bool IsValid(string? value) =>
        !string.IsNullOrWhiteSpace(value)
        && value.Length is >= 17 and <= 20
        && ulong.TryParse(value, out _);

    public static bool TryNormalizeOptional(string? value, out string? normalized)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            normalized = null;
            return true;
        }

        var trimmed = value.Trim();
        if (IsValid(trimmed))
        {
            normalized = trimmed;
            return true;
        }

        normalized = null;
        return false;
    }
}