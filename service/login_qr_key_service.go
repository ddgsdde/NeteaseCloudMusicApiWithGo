package service

import (
	"github.com/gin-gonic/gin"
	"singo/util"
)

type LoginQrKeyService struct {
	Type string `form:"type"`
}

func (service *LoginQrKeyService) LoginQrKey(c *gin.Context) map[string]interface{} {
	cookies := c.Request.Cookies()
	options := &util.Options{
		Crypto: "weapi",
		Ua:     "pc",
		Cookies: cookies,
	}
	data := make(map[string]string)
	data["type"] = "1"

	reBody, _ := util.CreateRequest("POST", "https://music.163.com/weapi/login/qrcode/unikey", data, options)
	return reBody
}
