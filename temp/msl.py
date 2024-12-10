from myslideslive import SlidesLive

msl = SlidesLive('https://slideslive.com/39021974/'
                 'beyond-static-papers-'
                 'rethinking-how-we-share-scientific-understanding-in-ml')
msl.download_slides() # slide=(1074, 1075))
msl.compose_video()
