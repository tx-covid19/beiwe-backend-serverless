#redcap survey

#Beiwe survey

- responses to questions, as strings
- completion statistics

{
        'survey-<survey_id>':[
                {
                    'begin_timestamp': 156000000,
                    'end_timestamp': 1560000000,
                    'subsores_json_string': 'xxxx',
                    'num_scheduled': ,
                    'num_completed': ,
                }
        ]
}


#device motion (accelerometer)

- amount of time device is on person
- amount of time spent sedentary

{
        'accelerometer':[
            {
                'begin_timestamp': 156000000,
                'end_timestamp': 1560000000,
                'duration_phone_on_person_seconds': 15,
                'duration_sedentary_seconds': 24
            }
        ]
}


#GPS

- number of locations visited
- total distance traveled
- radius of travel area (sum of squares)

{
	'data_type': 'gps',
	'observations: [
                {
                        'first_timestamp': 155600000,
                        'last_timestamp': 155600000,
                        'number_locations_visited': 5
                        'travel_radius_miles_mean': 4022,
			'travel_radius_miles_sum_product': 44,
			'travel_radius_miles_sum_squares': 55,
			'path_length_miles': 15,
			'num_data_points': 256
		},
	]


}

#identifiers

{
    'identifiers': [
         { 
             'first_timestamp': 155600000,
             'last_timestamp': 144444444,
             'phone_version':
             'phone_model':
             'phone_manufacturer'
             'operating_system':
             'operating_system_version':
    }]
}

#proximity
{
    'duration_on_phone': [
         { 
             'first_timestamp': 155600000,
             'last_timestamp': 144444444,
             'duration_on_phone_seconds':
    }]
}


#reachability
{
    'reachability': [
         { 
             'first_timestamp': 155600000,
             'last_timestamp': 144444444,
             'duration_wifi_seconds':
    }]
}

#ScreenTime
{
    'screen_time': [
         { 
             'first_timestamp': 155600000,
             'last_timestamp': 144444444,
             'duration_screen_unlocked':
    }]
}


