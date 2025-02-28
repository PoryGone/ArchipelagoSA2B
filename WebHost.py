import os
import sys
import multiprocessing
import logging
import typing

import ModuleUpdate

ModuleUpdate.requirements_files.add(os.path.join("WebHostLib", "requirements.txt"))
ModuleUpdate.update()

# in case app gets imported by something like gunicorn
import Utils

Utils.local_path.cached_path = os.path.dirname(__file__)

from WebHostLib import app as raw_app
from waitress import serve

from WebHostLib.models import db
from WebHostLib.autolauncher import autohost, autogen
from WebHostLib.lttpsprites import update_sprites_lttp
from WebHostLib.options import create as create_options_files

from worlds.AutoWorld import AutoWorldRegister

configpath = os.path.abspath("config.yaml")
if not os.path.exists(configpath):  # fall back to config.yaml in home
    configpath = os.path.abspath(Utils.user_path('config.yaml'))


def get_app():
    app = raw_app
    if os.path.exists(configpath):
        import yaml
        app.config.from_file(configpath, yaml.safe_load)
        logging.info(f"Updated config from {configpath}")
    db.bind(**app.config["PONY"])
    db.generate_mapping(create_tables=True)
    return app


def create_ordered_tutorials_file() -> typing.List[typing.Dict[str, typing.Any]]:
    import json
    import shutil
    worlds = {}
    data = []
    for game, world in AutoWorldRegister.world_types.items():
        if hasattr(world.web, 'tutorials') and (not world.hidden or game == 'Archipelago'):
            worlds[game] = world
    for game, world in worlds.items():
        # copy files from world's docs folder to the generated folder
        source_path = Utils.local_path(os.path.dirname(sys.modules[world.__module__].__file__), 'docs')
        target_path = Utils.local_path("WebHostLib", "static", "generated", "docs", game)
        files = os.listdir(source_path)
        for file in files:
            os.makedirs(os.path.dirname(Utils.local_path(target_path, file)), exist_ok=True)
            shutil.copyfile(Utils.local_path(source_path, file), Utils.local_path(target_path, file))
        # build a json tutorial dict per game
        game_data = {'gameTitle': game, 'tutorials': []}
        for tutorial in world.web.tutorials:
            # build dict for the json file
            current_tutorial = {
                'name': tutorial.tutorial_name,
                'description': tutorial.description,
                'files': [{
                    'language': tutorial.language,
                    'filename': game + '/' + tutorial.file_name,
                    'link': f'{game}/{tutorial.link}',
                    'authors': tutorial.author
                }]
            }

            # check if the name of the current guide exists already
            for guide in game_data['tutorials']:
                if guide and tutorial.tutorial_name == guide['name']:
                    guide['files'].append(current_tutorial['files'][0])
                    break
            else:
                game_data['tutorials'].append(current_tutorial)

        data.append(game_data)
    with open(Utils.local_path("WebHostLib", "static", "generated", "tutorials.json"), 'w', encoding='utf-8-sig') as json_target:
        generic_data = {}
        for games in data:
            if 'Archipelago' in games['gameTitle']:
                generic_data = data.pop(data.index(games))
        sorted_data = [generic_data] + sorted(data, key=lambda entry: entry["gameTitle"].lower())
        json.dump(sorted_data, json_target, indent=2, ensure_ascii=False)
    return sorted_data


if __name__ == "__main__":
    multiprocessing.freeze_support()
    multiprocessing.set_start_method('spawn')
    logging.basicConfig(format='[%(asctime)s] %(message)s', level=logging.INFO)
    try:
        update_sprites_lttp()
    except Exception as e:
        logging.exception(e)
        logging.warning("Could not update LttP sprites.")
    app = get_app()
    create_options_files()
    create_ordered_tutorials_file()
    if app.config["SELFLAUNCH"]:
        autohost(app.config)
    if app.config["SELFGEN"]:
        autogen(app.config)
    if app.config["SELFHOST"]:  # using WSGI, you just want to run get_app()
        if app.config["DEBUG"]:
            app.run(debug=True, port=app.config["PORT"])
        else:
            serve(app, port=app.config["PORT"], threads=app.config["WAITRESS_THREADS"])
