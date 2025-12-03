package service

import (
	"encoding/base64"
	"github.com/gin-gonic/gin"
	"github.com/skip2/go-qrcode"
)

type LoginQrCreateService struct {
	Key  string `form:"key"`
	Qrimg string `form:"qrimg"`
}

func (service *LoginQrCreateService) LoginQrCreate(c *gin.Context) map[string]interface{} {
	answer := make(map[string]interface{})
	url := "https://music.163.com/login?codekey=" + service.Key

	if service.Qrimg != "" {
		qrCode, err := qrcode.Encode(url, qrcode.Medium, 256)
		if err != nil {
			answer["code"] = 500
			answer["msg"] = "Generate QR code failed"
			return answer
		}
		answer["qrimg"] = "data:image/png;base64," + base64.StdEncoding.EncodeToString(qrCode)
		answer["qrurl"] = url
	} else {
		answer["qrurl"] = url
	}
	answer["code"] = 200
	return answer
}
