GEMINI_API_KEY = "AIzaSyAwlSVufxkTFCnu9e54zTs5QAdmIlg-_-8"  

import google.generativeai as genai

generation_config = {
    "temperature": 0.7,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
}


model = genai.GenerativeModel(
    model_name="gemini-2.5-flash",
    generation_config=generation_config,

)


query="WHo is virat kohli ?"

response=model.generate_content(query)

print(response)