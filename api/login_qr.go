package api

import (
	"github.com/gin-gonic/gin"
	login_qr "singo/service/login_qr"
)

func LoginQrKey(c *gin.Context) {
	var service login_qr.LoginQrKeyService
	if err := c.ShouldBind(&service); err == nil {
		res := service.LoginQrKey(c)
		c.JSON(200, res)
	} else {
		c.JSON(200, ErrorResponse(err))
	}
}

func LoginQrCreate(c *gin.Context) {
	var service login_qr.LoginQrCreateService
	if err := c.ShouldBind(&service); err == nil {
		res := service.LoginQrCreate(c)
		c.JSON(200, res)
	} else {
		c.JSON(200, ErrorResponse(err))
	}
}

func LoginQrCheck(c *gin.Context) {
	var service login_qr.LoginQrCheckService
	if err := c.ShouldBind(&service); err == nil {
		res := service.LoginQrCheck(c)
		c.JSON(200, res)
	} else {
		c.JSON(200, ErrorResponse(err))
	}
}
