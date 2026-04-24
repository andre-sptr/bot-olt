package scheduler

import (
	"log"
	"time"
)

// Schedule: 08:00, 10:00, 12:00, 14:00, 16:00, 18:00, 20:00
var jadwal = []int{10, 11, 12, 13, 14, 15, 20}

// task will be executed every 2 hours from 08:00 - 20:00
func Run(task func()) {
	log.Println("Scheduler aktif — jadwal kirim:", formatJadwal())

	for {
		now := time.Now()
		next := nextRun(now)
		durasi := time.Until(next)

		log.Printf("Menunggu pengiriman berikutnya: %s (%s lagi)",
			next.Format("02/01/06 15:04"), durasi.Round(time.Second))

		time.Sleep(durasi)

		log.Println("Waktu kirim!")
		task()
	}
}

// calculate next run time
func nextRun(now time.Time) time.Time {
	for _, jam := range jadwal {
		t := time.Date(now.Year(), now.Month(), now.Day(), jam, 0, 0, 0, now.Location())
		if t.After(now) {
			return t
		}
	}
	// All schedule today has passed
	besok := now.AddDate(0, 0, 1)
	return time.Date(besok.Year(), besok.Month(), besok.Day(), jadwal[0], 0, 0, 0, now.Location())
}

func formatJadwal() string {
	s := ""
	for i, jam := range jadwal {
		if i > 0 {
			s += ", "
		}
		s += time.Date(0, 0, 0, jam, 0, 0, 0, time.UTC).Format("15:04")
	}
	return s
}
