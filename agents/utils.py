import os
from dotenv import load_dotenv
from deepgram import DeepgramClient, PrerecordedOptions, FileSource

load_dotenv()

class DeepgramWrapper:
    def __init__(self):
        api_key = os.getenv("DG_API_KEY")
        self.client = DeepgramClient(api_key)

    def get_audio_intelligence(self, audio_bytes: bytes):
        try:
            payload: FileSource = {"buffer": audio_bytes}

            options = PrerecordedOptions(
                model="nova-2",
                sentiment=True,
                intents= True,

            )

            response = self.client.listen.prerecorded.v("1").transcribe_file(payload, options)
            api_result = response.to_dict()
            
            return self.extract_context(api_result)
        except Exception as e:
            print(f"Exception: {e}")
            return None

    def extract_context(self, api_result: dict):
        context = {
            "sentiments": None,
            "intents": None
        }

        try:
            sentiments = api_result.get("results", {}).get("sentiments", {})
            if sentiments:
                context["sentiments"] = {
                    "average": sentiments.get("average"),
                    "segments": [
                        {
                            "text": seg.get("text"),
                            "sentiment": seg.get("sentiment"),
                            "score": seg.get("sentiment_score"),
                        }
                        for seg in sentiments.get("segments", [])
                    ]
                }

            intents = api_result.get("results", {}).get("intents", {})
            if intents:
                extracted_intents = []
                for seg in intents.get("segments", []):
                    for intent in seg.get("intents", []):
                        extracted_intents.append({
                            "text": seg.get("text"),
                            "intent": intent.get("intent"),
                            "confidence": intent.get("confidence_score"),
                        })

                context["intents"] = extracted_intents

        except Exception as e:
            print(f"Error extracting context: {e}")

        return context

