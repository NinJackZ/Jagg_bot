# Jagg_bot
Custom Discord Bot that does whatever i want it to do

## Requirements
Install via pip using 
```
pip install -r requirements.txt
```

## Commands
```
/ping
/join
/faceit
```
/ping - Test bot connection
/join - Join users currently connected voice chat, enables profanity auto-detect kick
/faceit - Provides a local leaderboard using all hardcoded server members with a faceit account


## Considerations
To use on server input server ids into array
```
GUILD_IDS = [
    DISCORD_SERVER_ID, # Server 1
    DISCORD_SERVER_ID_2, # Server 2
]i

```

To use FACEIT leaderboard add users into array
```
FACEIT_PLAYERS = {
    DISCORD_USER_ID: "FACEIT Username",
    DISCORD_USER_ID_2: "FACEIT Username #2",
    DISCORD_USER_ID_3: "FACEIT Username #3",
}
```