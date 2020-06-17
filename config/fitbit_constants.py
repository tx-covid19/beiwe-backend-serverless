TIME_SERIES_TYPES = {
    'activities/calories': 'float',
    'activities/caloriesBMR': 'float',
    'activities/steps': '+int',
    'activities/distance': 'float',
    'activities/minutesSedentary': '+int',
    'activities/minutesLightlyActive': '+int',
    'activities/minutesFairlyActive': '+int',
    'activities/minutesVeryActive': '+int',
    'activities/activityCalories': 'float',
    'body/bmi': 'float',
    'body/fat': 'float',
    'body/weight': 'float',
    'foods/log/caloriesIn': 'float',
    'foods/log/water': 'float',
    'activities/heart': 'json',
    'sleep': 'json'
}

INTRA_TIME_SERIES_TYPES = {
    'activities/calories': {'type': 'float', 'interval': '1min'},
    'activities/steps': {'type': '+int', 'interval': '1min'},
    'activities/distance': {'type': 'float', 'interval': '1min'},
    'activities/heart': {'type': 'float', 'interval': '1sec'},
}
