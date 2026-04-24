package whatsapp

import (
	"bytes"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"

	"bges-bot/config"
)

// sendTextRequest representing the request body for WAHA sendText API.
type sendTextRequest struct {
	Session string `json:"session"`
	ChatID  string `json:"chatId"`
	Text    string `json:"text"`
}

// maxRetries is the maximum number of retries.
const maxRetries = 3

// retryDelay is the delay between retries.
const retryDelay = 2 * time.Second

// sending text message to WhatsApp chat via WAHA API.
// With retry logic to handle connection errors.
func SendTextMessage(cfg config.Config, chatID, message string) error {
	url := fmt.Sprintf("%s/api/sendText", cfg.WahaURL)

	payload := sendTextRequest{
		Session: cfg.WahaSession,
		ChatID:  chatID,
		Text:    message,
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return fmt.Errorf("gagal membuat JSON payload: %w", err)
	}

	client := &http.Client{
		Timeout: 60 * time.Second,
	}

	var lastErr error
	for attempt := 1; attempt <= maxRetries; attempt++ {
		if attempt > 1 {
			log.Printf("   ⏳ Retry %d/%d...", attempt, maxRetries)
			time.Sleep(retryDelay)
		}

		req, err := http.NewRequest("POST", url, bytes.NewBuffer(body))
		if err != nil {
			return fmt.Errorf("gagal membuat HTTP request: %w", err)
		}

		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Accept", "application/json")
		req.Header.Set("X-Api-Key", cfg.WahaAPIKey)

		resp, err := client.Do(req)
		if err != nil {
			lastErr = fmt.Errorf("gagal mengirim request (attempt %d): %w", attempt, err)
			log.Printf("   ⚠️ %v", lastErr)
			continue
		}
		resp.Body.Close()

		if resp.StatusCode == http.StatusOK || resp.StatusCode == http.StatusCreated {
			return nil
		}

		lastErr = fmt.Errorf("WAHA mengembalikan status %d (attempt %d)", resp.StatusCode, attempt)
		log.Printf("   ⚠️ %v", lastErr)
	}

	return fmt.Errorf("gagal mengirim pesan setelah %d percobaan: %w", maxRetries, lastErr)
}

// sending multiple messages in order with delay between messages.
func SendMessages(cfg config.Config, chatID string, messages []string, delay time.Duration) error {
	totalMessages := len(messages)

	for i, msg := range messages {
		log.Printf("📤 Mengirim pesan %d/%d ke %s...", i+1, totalMessages, chatID)

		if err := SendTextMessage(cfg, chatID, msg); err != nil {
			return fmt.Errorf("gagal mengirim pesan %d/%d: %w", i+1, totalMessages, err)
		}

		log.Printf("✅ Pesan %d/%d terkirim", i+1, totalMessages)

		if i < totalMessages-1 {
			time.Sleep(delay)
		}
	}

	return nil
}
