using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

var client = new HttpClient { BaseAddress = new Uri("http://localhost:8001") };

var requestJson = JsonSerializer.Serialize(new
{
    model = "Qwen2.5-Coder-7B-Instruct-int4-ov",
    messages = new[]
    {
        new { role = "system", content = "You are a helpful coding assistant." },
        new { role = "user",   content = "Write a C# method that checks if a string is a palindrome. Keep it concise." }
    },
    max_tokens = 300
});

Console.WriteLine("Sending prompt to OVMS...\n");

var content  = new StringContent(requestJson, Encoding.UTF8, "application/json");
var response = await client.PostAsync("/v3/chat/completions", content);
var body     = await response.Content.ReadAsStringAsync();

if (!response.IsSuccessStatusCode)
{
    Console.WriteLine($"Error {(int)response.StatusCode}: {body}");
    return;
}

var doc   = JsonNode.Parse(body)!;
var reply = doc["choices"]![0]!["message"]!["content"]!.GetValue<string>();
var model = doc["model"]!.GetValue<string>();
var usage = doc["usage"]!;

Console.WriteLine($"Model  : {model}");
Console.WriteLine($"Tokens : {usage["prompt_tokens"]} prompt + {usage["completion_tokens"]} completion\n");
Console.WriteLine("--- Response ---");
Console.WriteLine(reply);
