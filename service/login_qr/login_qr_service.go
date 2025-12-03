package service

import (
	"singo/util"

	"github.com/gin-gonic/gin"
)

type LoginQrKeyService struct{}

func (service *LoginQrKeyService) LoginQrKey(c *gin.Context) map[string]interface{} {
	options := &util.Options{
		Crypto:  "weapi",
		Ua:      "pc",
		Cookies: c.Request.Cookies(),
	}
	data := make(map[string]string)
	data["type"] = "1"
	reBody, cookies := util.CreateRequest("POST", `https://music.163.com/weapi/login/qrcode/unikey`, data, options)

	// Pass cookies back to client
	util.SetCookies(c, cookies)
	return reBody
}

type LoginQrCreateService struct {
	Key string `json:"key" form:"key"`
}

func (service *LoginQrCreateService) LoginQrCreate(c *gin.Context) map[string]interface{} {
	// The node.js version just constructs the url: https://music.163.com/login?codekey={key}
	// And maybe generates a QR code image from it.
	// But simply returning the URL is enough for the client to generate QR.

	url := "https://music.163.com/login?codekey=" + service.Key

	return map[string]interface{}{
		"code": 200,
		"data": map[string]string{
			"qrurl": url,
			"qrimg": "", // Optional: generate QR image base64 if needed, but MA might just need the URL or text
		},
	}
}

type LoginQrCheckService struct {
	Key string `json:"key" form:"key"`
}

func (service *LoginQrCheckService) LoginQrCheck(c *gin.Context) map[string]interface{} {
	options := &util.Options{
		Crypto:  "weapi",
		Ua:      "pc",
		Cookies: c.Request.Cookies(),
	}
	data := make(map[string]string)
	data["key"] = service.Key
	data["type"] = "1"

	reBody, cookies := util.CreateRequest("POST", `https://music.163.com/weapi/login/qrcode/client/login`, data, options)

	util.SetCookies(c, cookies)
	return reBody
}
