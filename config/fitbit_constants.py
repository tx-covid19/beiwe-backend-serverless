TIME_SERIES_TYPES = {
    'activities/calories': 'float',
    'activities/caloriesBMR': 'float',
    'activities/steps': '+int',
    'activities/distance': 'float',
    # may not work in some devices
    #    'activities/floors': '+int',
    #    'activities/elevation': 'float',
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
    'activities/calories': 'float',
    'activities/steps': '+int',
    'activities/distance': 'float',
    'activities/heart': 'float',
}