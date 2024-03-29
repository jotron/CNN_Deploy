from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse
from starlette.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
import uvicorn, aiohttp, asyncio
import json
from io import BytesIO

from fastai import *
from fastai.vision import *
from fastai.version import __version__

modelTypes = {
    "resnet18": models.resnet18,
    "resnet34": models.resnet34,
    "resnet50": models.resnet50,
    "resnet101": models.resnet101,
    "resnet152": models.resnet152,
}

path = Path(__file__).parent

with open("modelDefinition.json") as f:
    modelDefs = json.load(f)

app = Starlette()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["X-Requested-With", "Content-Type"],
)
app.mount("/static", StaticFiles(directory="app/static"))



async def setup_learners():
    learners = []
    for m in modelDefs:
        modelFileName = m["modelFileName"]
        data_bunch = ImageDataBunch.single_from_classes(
            path, m["classes"], tfms=get_transforms(), size=m["imageSize"]
        ).normalize(imagenet_stats)
        learn = create_cnn(data_bunch, modelTypes[m["modelType"]])
        learn.load(m["modelFileName"])
        learners.append(learn)
    return learners


loop = asyncio.get_event_loop()
tasks = [asyncio.ensure_future(setup_learners())]
learners = loop.run_until_complete(asyncio.gather(*tasks))[0]
loop.close()


@app.route("/")
def index(request):
    html = path / "view" / "index.html"
    return HTMLResponse(html.open().read())


@app.route("/analyze", methods=["POST"])
async def analyze(request):
    data = await request.form()
    img_bytes = await (data["file"].read())
    img = open_image(BytesIO(img_bytes))
    predictions = []
    top_losses = []
    for learn in learners:
        print("prediction:", learn.predict(img)[0])
        pred_class, pred_idx, losses = learn.predict(img)
        predictions.append(pred_class) # same as learn.predict(img)[0]
        top_losses.append(losses)

    print("length of predictions list:", len(predictions))

    top3_preds = []
    for c in range(len(predictions)):
        print("modelName:", modelDefs[c]["name"])
        print("type of predictions[c]:", type(predictions[c]))
        print("prediction:", predictions[c])
        print("textResult:", "modelName:" + modelDefs[c]["name"] + " - prediction:" + str(predictions[c]))

        top_preds = sorted(zip(modelDefs[c]["classes"], map(float, top_losses[c])), key=lambda p: p[1], reverse=True)
        top3 = top_preds[0:3]
        top3_preds.append(top3)
        print("top-3 preds:", str(top3))

    return JSONResponse(
        {
            "textResult": [
                "<strong>model name:</strong> "
                + modelDefs[c]["name"]
                + ",<br /><strong>prediction:</strong> <span class='pred'>"
                + str(predictions[c])
                + "</span><br />"
                for c in range(len(predictions))
            ],
            "result": [
                {"modelName": modelDefs[c]["name"], "prediction": str(predictions[c])}
                for c in range(len(predictions))
            ],
            "top_3_result": [
                {"modelName": modelDefs[c]["name"], "prediction": str(top3_preds[c])}
                for c in range(len(top3_preds))
            ]
        }
    )


if __name__ == "__main__":
    if "serve" in sys.argv:
        uvicorn.run(app, host="0.0.0.0", port=5042)
