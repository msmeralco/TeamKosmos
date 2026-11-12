"""Every model in the Sol kit, grouped. build_kit.py meshes, lays out and exports them."""
import models_a as A, models_b as B, models_c as C, models_d as D

WARM = ['#f08fb0', '#f6d44a', '#ffffff', '#e2483d']


def groups():
    g = {}
    g['houses'] = [
        A.house('house_a', lit=(0, 3), seed=3),
        A.house('house_b', wall='#f3c7a1', trim='#fbf5e9', lit=(1, 4), seed=4),
        A.house('house_c', wall='#bfe3cf', lit=(3,), seed=5),
        A.house('house_d', wall='#b9d8ec', trim='#fbf5e9', lit=(2, 5), seed=6),
        A.house('house_e', wall='#f2e3c4', roof='gable', roofc='#b8493a', floors=1, w=30, d=24, lit=(1,), seed=7),
        A.house('house_f', wall='#f0d67a', roof='gable', roofc='#3f6fa3', floors=1, w=30, d=24, lit=(0,), seed=8),
        A.house('house_g', wall='#e3a58a', roof='gable', roofc='#7c8590', floors=2, w=30, d=24, lit=(3, 5), seed=9),
        A.house('house_hero', wall='#f6e7cf', trim='#fbf5e9', floors=2, w=48, d=32, lit=(0, 1, 3, 4), seed=12),
        A.fence_gate('gate'), D.fence_seg('fence'), D.hedge('hedge'),
    ]
    g['buildings'] = [
        D.midrise('midrise_a', 1, floors=4, wall='#e8d9bd', accent='#d9644a'),
        D.midrise('midrise_b', 2, floors=5, wall='#c9dbe9', accent='#2f8f8a', lit_p=.45),
        D.sari_sari('sari_sari'), D.pavilion('pavilion'),
    ]
    g['nature'] = [
        B.palm('palm_a', 1), B.palm('palm_b', 2, h=28, lean=-3), B.palm('palm_c', 3, h=38, lean=2),
        B.round_tree('mango_a', 1), B.round_tree('mango_b', 2, h=13, R=11),
        B.round_tree('flame', 3, greens=['#4c9a3c', '#5fb04a', '#e2483d', '#f06a3c'], R=9),
        B.banana('banana', 1), B.bush('bush_a', 1), B.bush('bush_f', 2, flower=WARM),
    ]
    g['street'] = [
        B.lamp_post('lamp'), B.utility_pole('pole'), B.bench('bench'), B.bin_('bin'), B.hoop('hoop'), B.flag_ph('flag_ph'),
        B.jeepney('jeepney_a'), B.jeepney('jeepney_b', body='#2f9e8f', stripe='#f2c230', stripe2='#d1342f', seed=2),
        B.tricycle('tricycle_a'), B.van('van'), B.sedan('sedan_a'), B.sedan('sedan_b', body='#c9564a', seed=5),
        B.person('person_a'), B.person('person_b', shirt='#d1342f', pants='#2c3a52', hat='#e0c050', skin='#c68b5c'),
        B.person('person_c', shirt='#f2c230', pants='#33384a', skin='#f1c9a0', hair='#5a3a24'),
        B.person('person_d', shirt='#3c9a6a', pants='#4a4034', skin='#9a6a44', hair='#1e1a18'),
        B.person('person_e', shirt='#f4f4f0', pants='#2d3748', skin='#e0ac7c', hair='#8f8f94'),
        B.dog('dog'),
    ]
    g['cast'] = [
        # the sellers of slide 2, the crew of slide 4 and the owner of slide 5
        B.figure('seller_a', shirt='#33425c', vest='#f08a24', hat='#f2c230', skin='#c68b5c', hair='#1e1a18', pose='present', badge='#f4f4f0', seed=11),
        B.figure('seller_b', shirt='#2f9e8f', pants='#3a3f4a', hat='#f4f4f0', hat_kind='cap', skin='#8d5a3c', hair='#1e1a18', glasses=True, pose='wave', seed=12),
        B.figure('seller_c', shirt='#f4f4f0', pants='#1f2430', tie='#2a3f8f', skin='#f1c9a0', hair='#8f8f94', glasses=True, sleeves='long', pose='cross', seed=13),
        B.figure('installer_a', shirt='#f2c230', vest='#f08a24', hat='#f4f4f0', skin='#e0ac7c', hair='#2a1d16', pose='up', seed=14),
        B.figure('installer_b', shirt='#33425c', vest='#c8e04a', hat='#f2c230', skin='#9a6a44', hair='#1e1a18', pose='rest', seed=15),
        B.figure('owner', shirt='#d94f70', pants='#2c3a52', skin='#e0ac7c', hair='#2a1d16', hairstyle='long', pose='wave', seed=16),
    ]
    g['sol'] = [
        C.panel('panel'), C.battery('battery'), C.inverter('inverter'), C.sun_big('sun_big'), C.sol('sol'), C.coin('coin'),
        C.cloud('cloud_a', 1), C.cloud('cloud_b', 2, size=1.2), C.cloud('cloud_c', 3, size=0.9),
        C.cloud('storm_a', 4, storm=True, size=1.3), C.cloud('storm_b', 5, storm=True, size=1.1),
        C.passport('passport'), C.seal('seal'), C.chain_block('chain_block'),
        C.letters('SOL', px=5, name='word_sol'), C.letters('?', px=3, name='word_q', color='#ffb43a', emit=False),
        C.layer('layer_weather', 'weather', 1), C.layer('layer_tariff', 'tariff', 2),
        C.layer('layer_credit', 'credit', 3), C.layer('layer_prices', 'prices', 4),
        C.solar_rack('solar_rack'), C.meter_stand('meter_stand'), C.map_pin('map_pin'),
        C.flag_board('flag_board'), C.energy_cube('energy_big', True), C.energy_cube('energy_small', False), C.rec_slot('rec_slot'),
    ]
    g['ground'] = [
        D.grass('grass_a', 1), D.grass('grass_b', 2, flowers=WARM, pebbles=True), D.grass('grass_c', 3, dirt=True),
        D.driveway('yard_path'), D.street('street_h', 2), D.street('street_hx', 3, zebra=True), D.street_cross('street_cross'),
        D.plaza('plaza'), D.court('court'),
    ]
    g['far'] = [D.hills('hills_a', 1), D.hills('hills_b', 5, hmax=28, base='#6aa65d'), D.skyline('skyline_a', 1), D.skyline('skyline_b', 2)]
    return g
