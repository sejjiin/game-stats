"""Provides statistics on boardgamegeek(bgg) game collections and logged plays.
"""
import collections
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from typing import Dict
from urllib.request import HTTPError, urlopen
from xml.dom.minidom import parseString

BGG_API = 'https://boardgamegeek.com/xmlapi2'
LAMBDA_FRIENDLESS = 0.2303

# ------------------------------------------------------------------------------
# CLASSES
# ------------------------------------------------------------------------------


@dataclass
class Game:
    """
    Board game data including status information and dates of plays.
    """
    game_id: int
    game_name: str
    is_owned: bool
    is_previously_owned: bool
    plays: list[datetime]

# ------------------------------------------------------------------------------
# PUBLIC METHODS
# ------------------------------------------------------------------------------


def download_games(username: str) -> list[Game]:
    """Returns baseless games statistics for a given BGG user.

    Args:
        username: the BGG username
    """
    # Download games
    url = f"{BGG_API}/collection?username={username}&brief=1&excludesubtype=boardgameexpansion"
    dom = parseString(__urlopen_retry(url))
    games: Dict[int, Game] = {}
    for item in dom.getElementsByTagName('item'):
        game_id = item.getAttribute('objectid')
        name = item.getElementsByTagName('name')[0].firstChild.data
        status = item.getElementsByTagName('status')[0]
        is_owned = status.getAttribute('own') == "1"
        is_prev_owned = status.getAttribute('prevowned') == "1"
        if is_owned or is_prev_owned:
            games[game_id] = Game(game_id, name, is_owned, is_prev_owned, [])

    # Download plays
    first_page = __download_bgg_plays(username, 1)
    first_dom = parseString(first_page)
    root = first_dom.getElementsByTagName('plays')[0]

    # total pages will be the totals plays / page size (100) + 1
    # additional page for the sub-100 remainder.
    total_pages = int(int(root.getAttribute('total')) / 100) + 1
    plays = [first_page]

    # Create a function with partial arguments to allow for multiple args to be
    # passed to the target function via the thread pool executor map function.
    func = partial(__download_bgg_plays, username)

    with ThreadPoolExecutor(max_workers=5) as executor:
        # total_page +1 because end param is exclusive
        results = executor.map(func, range(2, total_pages + 1))
        for result in results:
            plays.append(result)

    for play in plays:
        dom = parseString(play)
        for play_dom in dom.getElementsByTagName('play'):
            play_quantity = int(play_dom.getAttribute('quantity'))
            item = play_dom.getElementsByTagName('item')[0]
            object_id = item.getAttribute('objectid')
            if object_id not in games:
                continue
            game = games[object_id]
            date_str = play_dom.getAttribute('date')
            date = datetime.strptime(date_str, '%Y-%m-%d')

            # Handle play entries that encompass multiple plays.
            i = 0
            while i < play_quantity:
                game.plays.append(date)
                i = i + 1

    return list(map(lambda k: games[k], games.keys()))


def get_base_stats(plays: list[int], precision: int) -> Dict[str, float]:
    """Returns basic play statistics.

    Args:
        plays: a list of integers representing play counts of games
        precision: desired precision of decimal digits in returned statistics
    """
    mean = statistics.mean(plays)
    median = statistics.median(plays)
    _h_index = get_h_index(plays)
    return {'mean': round(mean, precision), 'median': median, 'h-index': _h_index}


def get_coins(plays: list[int]) -> dict[str, int]:
    """Returns coin base statistics.

    Returns number of games that have been played 5 (nickel), 10 (dime),
    25 (quarter), etc. times.

    Args:
        plays: a list of integers where each cell indicates a play count of a game.
    """
    nickels = 0
    dimes = 0
    quarters = 0
    halves = 0
    dollars = 0
    for play in plays:
        if play >= 100:
            dollars += 1
        elif play >= 50:
            halves += 1
        elif play >= 25:
            quarters += 1
        elif play >= 10:
            dimes += 1
        elif play >= 5:
            nickels += 1

    return {'nickels': nickels, 'dimes': dimes, 'quarters': quarters,
            'halves': halves, 'dollars': dollars}


def get_h_index(plays: list[int]) -> int:
    """Returns the number of games that have been played at least that number of times.

    Example: h-index of 6 indicates 6 games have been played at least 6 times.

    Args:
        plays: a list of integers where each cell indicates a play count of a game.
    """
    plays_desc = sorted(plays, reverse=True)
    h_index = 0
    while h_index + 1 < len(plays_desc) and h_index + 1 <= plays_desc[h_index]:
        h_index += 1
    return h_index


def get_friendless(plays: list[int], precision: int) -> dict[str, float]:
    """Returns friendless metrics.

    Args:
        plays: a list of integers where each cell indicates a play count of a game.

    Returns:
      A dict mapping of friendless metrics.

      {'friendlessMetric': 3,
       'continuousFriendlessMetric': 4.53,
       'utilization': .65}
    """
    plays_heavy = len(list(filter(lambda x: x >= 10, plays)))
    plays_none = len(list(filter(lambda x: x == 0, plays)))
    plays_asc = sorted(plays)

    friendless_metric = 0
    if plays_heavy < plays_none:
        friendless_metric = plays_heavy - plays_none
    elif plays_heavy == len(plays):
        friendless_metric = plays_asc[plays_heavy - 1]
    else:
        friendless_metric = plays_asc[plays_heavy]

    avg_cdf = __get_avg_cdf(plays, LAMBDA_FRIENDLESS)
    continuous_friendless = round(__get_inverse_cdf(
        avg_cdf, LAMBDA_FRIENDLESS), precision)
    utilization = round(avg_cdf, precision)
    return {'friendlessMetric': friendless_metric,
            'continuousFriendlessMetric': continuous_friendless,
            'utilization': utilization}


def get_baseless_next_plays(games: list[Game]):
    """Calculates the effect of playing a specific game on baseless stats.

    Args:
        plays: a list of Games.

    Returns:
      A list of dictionaries where each entry represents the baseless-metric
      effect of playing the game represented by that dictionary.
    """
    result = []
    # h_index = get_h_index(__get_plays(baseless_stats))
    # h_index_cusp_games = __get_h_index_cusp_games(baseless_stats, h_index)
    plays = list(map(lambda game: game.plays, games))

    optimum_size = get_baseless_optimum_size(plays)
    for game in games:
        obj = {}
        obj['name'] = game.game_name
        obj['currentPlays'] = len(game.plays)
        if game.plays:
            obj['latestPlay'] = max(game.plays).strftime('%m/%d/%Y')
            obj['meanPlayAgeYears'] = round(__get_plays_cumulative_days_old(
                game.plays) / len(game.plays) / 365.25, 2)

        # baseless_frequency = stat.get_baseless_frequency_score()
        # baseless_mean_recency = stat.get_baseless_mean_recency_score()
        baseless_frecency = __get_baseless_frecency_score(game.plays)
        baseless_age_adjusted_plays = sum(
            map(__get_baseless_recency, game.plays))

        # next_play_baseless_frecency = stat.get_next_play_baseless_frecency_score()

        baseless = {}
        obj['baseless'] = baseless
        # baseless['meanRecency'] = round(baseless_mean_recency, 2)
        baseless['ageAdjustedPlays'] = round(baseless_age_adjusted_plays, 2)
        baseless['frecency'] = round(baseless_frecency, 3)

        # new_h_index = h_index
        # if stat.game.game_id in h_index_cusp_games:
        #     new_h_index += 1

        # Add a game play date of now to this game's plays to calculate
        # its effect on optimum collection size.
        adjusted_plays = game.plays.copy()
        adjusted_plays.append(datetime.now())
        adjusted_list_of_plays = list(
            map(lambda g, game_id=game.game_id, adjusted=adjusted_plays:
                adjusted if g.game_id == game_id
                else g.plays, games))
        next_play_optimum_size = get_baseless_optimum_size(
            adjusted_list_of_plays)
        baseless['optimumSizeGain'] = round(
            next_play_optimum_size - optimum_size, 3)

        next_play_frecency = __get_baseless_frecency_score(adjusted_plays)
        baseless['frecencyGain'] = round(
            next_play_frecency - baseless_frecency, 3)

        result.append(obj)

    return sorted(result, key=lambda x: x['baseless']['optimumSizeGain'], reverse=True)


def get_baseless_optimum_size(play_dates: list[list[datetime]]) -> float:
    """Returns an optimum game collection size based on baseless statistics.

    Args:
        play_dates: a list of lists of plays where each list of plays represent dates of
            plays of a distinct game. For example:

            Outer list item 0: [[2020-12-3],[2021-3-23],[2021-4-18]] --- dates Codenames was played
            Outer list item 1: [[2021-07-03],[2021-07-04]] --- dates Ticket to Ride was played
            Outer list item 2: [[2022-11-01],[2019-05-18]] --- dates Settler of Catan was played
    """
    # h_index = get_h_index(__get_plays(baseless_stats))
    # legacy algorithm: return h_index + 1.5 * baseless_frecency_sum

    return 2 * sum(map(__get_baseless_frecency_score, play_dates))

# ------------------------------------------------------------------------------
# PRIVATE STATISTIC METHODS
# ------------------------------------------------------------------------------


def __get_baseless_frecency_score(play_dates: list[datetime]) -> float:
    """Return a composite score based on both the frequency and recency of each play."""

    # Adjust total number of plays based on recency of plays
    adjusted_num_plays = sum(map(__get_baseless_recency, play_dates))

    return __get_baseless_frequency_score(adjusted_num_plays)


def __get_baseless_recency(play_date: datetime) -> float:
    delta = datetime.today() - play_date
    play_age_in_years = delta.days / 365.25
    return math.exp(-.04 * math.pow(play_age_in_years, 2))


def __get_baseless_frequency_score(num_plays: float) -> float:
    return __get_cdf(num_plays, LAMBDA_FRIENDLESS)
    # return get_logistic(num_plays, 1, 0.5, 6.5)


def __get_cdf(x_var, _lambda):
    """Gets the result of an exponential distributed cumulative distribution function.

    F_x(x; lambda) = 1 - e^(-lambda * x) -- e = Euler's number

    Args:
        x_var: function x parameter
        lambda: rate parameter

    See: https://en.wikipedia.org/wiki/Cumulative_distribution_function#Examples
    """
    return 1.0 - math.exp(-_lambda * float(x_var))


def __get_ccdf(x_var, rate):
    """Gets the results of a complementary exponential distributed cumulative distribution function

    F_x(x; lambda) = 1 - (1 - e^(-lambda * x)) -- e = Euler's number

    Args:
        x_var: function x parameter
        lambda: rate parameter

    See: https://en.wikipedia.org/wiki/Cumulative_distribution_function#Complementary_cumulative_distribution_function_(tail_distribution)
    """
    return 1.0 - __get_cdf(x_var, rate)


# def __get_logistic(x, l, k, x0):
#     return 1.0 / (1 + math.exp(-k * (x - x0)))

def __get_h_index_cusp_games(baseless_stats, h_index):
    """
    Returns game IDs that will result in an h-index increase on its next play
    """
    result = []
    stats_by_plays = __group_by_plays(baseless_stats)

    # Extract # of games at each play count. The resulting
    # key-value structure is play-count:number-of-games-with-that-play-count
    counter = collections.Counter(
        list(map(lambda stat: int(len(stat.plays)), baseless_stats)))

    play_counts = list(counter.keys())
    for play_count in play_counts:

        # adjust plays in counter - if a game is played, the # of games at
        # the current play count will decrease by one and the # of games
        # at the current play count +1 will increase by one.
        counter[play_count] -= 1
        counter[play_count + 1] += 1

        # calculate stats
        plays_list = list(counter.elements())
        new_h_index = get_h_index(plays_list)

        # record for all applicable games of play count
        if new_h_index > h_index:
            for stat in stats_by_plays[play_count]:
                result.append(stat.game.game_id)

        # reset plays
        counter[play_count] += 1
        counter[play_count + 1] -= 1

    return result


def __group_by_plays(baseless_stats):
    result = {}
    for stat in baseless_stats:
        num_plays = len(stat.plays)
        if not num_plays in result:
            result[num_plays] = []
        result[num_plays].append(stat)
    return result


def __get_avg_cdf(plays, _lambda):
    cdf_list = map(lambda x: __get_cdf(x, _lambda), plays)
    return statistics.mean(cdf_list)


def __get_inverse_cdf(avg_cdf, _lambda):
    inverse_cdf = -math.log(1 - float(avg_cdf))/_lambda
    return inverse_cdf


def __get_plays_cumulative_days_old(plays: list[datetime]) -> float:
    result = 0
    for play in plays:
        delta = datetime.today() - play
        result += delta.days
    return result

# --------------------------------
# PRIVATE BGG XMLAPI METHODS
# --------------------------------


def __urlopen_retry(url: str) -> str:
    response, code = __urlopen(url)
    retries = 0
    while (code in (202, 429) and retries <= 2):

        # sleep 2, 4, 8 seconds for a 202
        # always sleep for 5 seconds for a 429
        retries += 1
        sleep_time = math.pow(2, retries) if code == 202 else 5
        print(f'{url} - sleeping for {sleep_time} seconds')
        time.sleep(sleep_time)

        response, code = __urlopen(url)

    if code == 202:
        raise Exception(f"Timeout waiting for {url} to be processed.")
    if code == 429:
        raise Exception("Too many requests")
    return response


def __urlopen(url: str) -> tuple[str, int]:
    print(f'{url} - urlopen')
    try:
        response = urlopen(url)
        print(f'{url} - {response.code} received')
        return response.read().decode('utf-8'), response.code
    except HTTPError as err:
        print(f'{url} - error {err.code} received')
        if err.code == 429:
            return '', 429
        else:
            raise


def __download_bgg_plays(username: str, page: int) -> str:
    url = f"{BGG_API}/plays?username={username}&excludesubtype=boardgameexpansion&page={page}"
    return __urlopen_retry(url)
