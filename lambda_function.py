import json
import sys

import baseless


def lambda_handler(event, context):
    username = event['username']
    max_baseless_results = 99
    if 'maxBaselessResults' in event:
        try:
            max_baseless_results = int(event['maxBaselessResults'])
        except ValueError:
            pass
    stats = get_stats(username, max_baseless_results)
    return stats


def get_stats(username: str, max_next_play_results: int):
    games = baseless.download_games(username)

    owned_games = list(filter(lambda game: game.is_owned, games))
    plays = list(map(lambda game: game.plays, games))
    owned_play_counts = list(map(lambda game: len(game.plays), owned_games))

    output = {}
    output['baseStats'] = baseless.get_base_stats(owned_play_counts, 2)
    output['coins'] = baseless.get_coins(owned_play_counts)
    output['currentSize'] = len(owned_games)

    output['baselessOptimumSize'] = round(
        baseless.get_baseless_optimum_size(plays), 2)
    # output['baselessMeanFrecencyScore'] = round(
    #     baseless.get_mean_baseless_frecency_score(baseless_stats), 3)
    output['friendlessStats'] = baseless.get_friendless(owned_play_counts, 2)
    output['baselessNextPlays'] = baseless.get_baseless_next_plays(owned_games)[
        :max_next_play_results]
    return output


if len(sys.argv) > 1:
    if len(sys.argv) > 2:
        print(json.dumps(get_stats(sys.argv[1], int(sys.argv[2])), indent=2))
    else:
        print(json.dumps(get_stats(sys.argv[1], 99), indent=2))
else:
    print(json.dumps(get_stats('fuddman', 0), indent=2))
