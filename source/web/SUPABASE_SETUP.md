# Flight Game Supabase Setup

This is the simplest public setup for a shared scoreboard:

1. Host the game on GitHub Pages.
2. Store live scores in Supabase.
3. Let the browser game call Supabase directly over HTTPS.

## 1. Create the Supabase table

In the Supabase SQL editor, run:

```sql
create table if not exists public.flight_game_scores (
    player_key text primary key,
    name text not null,
    wins integer not null default 0,
    losses integer not null default 0,
    games_started integer not null default 0,
    updated_at timestamptz not null default now()
);

create or replace function public.flight_game_scores_set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists flight_game_scores_set_updated_at on public.flight_game_scores;

create trigger flight_game_scores_set_updated_at
before update on public.flight_game_scores
for each row
execute function public.flight_game_scores_set_updated_at();
```

## 2. Configure API access

Use the public project URL and anon key from Supabase.

Put them into [flight-game-config.json](c:/Users/conor/Game%201/web/flight-game-config.json):

```json
{
  "supabaseUrl": "https://your-project-id.supabase.co",
  "supabaseAnonKey": "your-public-anon-key",
  "supabaseTable": "flight_game_scores",
  "scoreApiUrl": ""
}
```

For the GitHub-hosted site, place the same `flight-game-config.json` beside the published `index.html` file.

## 3. Recommended row-level security

The simplest version is to disable RLS on this table while you are prototyping. That is easy, but any visitor can write scores.

For a safer production setup, enable RLS and add only the specific policies you want to allow. If you want, the next step can be a more locked-down Supabase ruleset or moving score writes behind a Supabase Edge Function.

## 4. How the game uses it

When `supabaseUrl` and `supabaseAnonKey` are present:

1. The game loads the leaderboard directly from Supabase.
2. Starting a match increments `games_started` for both named players.
3. Finishing a full match increments the winner's `wins` and the loser's `losses`.

If the Supabase config is blank, the game falls back to the existing custom score API path when configured, or to no shared web scoreboard.