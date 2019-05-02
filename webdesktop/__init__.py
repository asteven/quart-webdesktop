from quart_trio import QuartTrio
#from quart import Quart


def create_app(mode='Development'):
    """In production create as app = create_app('Production')"""
    #app = Quart(__name__)
    app = QuartTrio(__name__)
    #app.config.from_object(f"config.{mode}")

    @app.route('/')
    async def index():
        return 'Hello, World!'

    from webdesktop import guacamole
    guacamole.init_app(app)

    return app
