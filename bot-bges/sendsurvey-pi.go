package main

import (
	"log"
	"os"

	"bges-bot/config"
	"bges-bot/formatter"
	"bges-bot/scheduler"
	"bges-bot/sheets"
	"bges-bot/whatsapp"
)

func main() {
	log.Println("Bot Survey PI - Mulai")

	cfg := config.DefaultConfig()
	log.Printf("Target grup: %s", cfg.GroupID)
	log.Printf("Sumber data: Google Sheets (GID: %s)", cfg.SheetGID)

	// run this command to send the message immediately (manually)
	if len(os.Args) > 1 && os.Args[1] == "--now" {
		log.Println("Mode: manual (--now)")
		kirimReport(cfg)
		return
	}

	log.Println("Mode: scheduler")
	scheduler.Run(func() {
		kirimReport(cfg)
	})
}

func kirimReport(cfg config.Config) {
	data, err := sheets.FetchData(cfg)
	if err != nil {
		log.Printf("Gagal mengambil data: %v", err)
		return
	}
	log.Printf("Berhasil mengambil %d order", len(data))

	message := formatter.FormatMessage(data)
	log.Printf("Pesan siap dikirim (%d karakter)", len(message))

	err = whatsapp.SendTextMessage(cfg, cfg.GroupID, message)
	if err != nil {
		log.Printf("Gagal mengirim pesan: %v", err)
		return
	}
	log.Println("Pesan berhasil terkirim!")
}
