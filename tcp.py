import asyncio
from tcputils import *
import random
import time


class Servidor:
    def __init__(self, rede, porta):
        self.rede = rede
        self.porta = porta
        self.conexoes = {}
        self.callback = None
        self.rede.registrar_recebedor(self._rdt_rcv)

    def registrar_monitor_de_conexoes_aceitas(self, callback):
        """
        Usado pela camada de aplicação para registrar uma função para ser chamada
        sempre que uma nova conexão for aceita
        """
        self.callback = callback

    def _rdt_rcv(self, src_addr, dst_addr, segment):
        src_port, dst_port, seq_no, ack_no, \
            flags, window_size, checksum, urg_ptr = read_header(segment)

        if dst_port != self.porta:
            # Ignora segmentos que não são destinados à porta do nosso servidor
            return
        if not self.rede.ignore_checksum and calc_checksum(segment, src_addr, dst_addr) != 0:
            print('descartando segmento com checksum incorreto')
            return

        payload = segment[4*(flags >> 12):]
        id_conexao = (src_addr, src_port, dst_addr, dst_port)

        new_src_addr = dst_addr
        new_dst_addr = src_addr

        new_src_port = dst_port
        new_dst_port = src_port

        if (flags & FLAGS_SYN) == FLAGS_SYN:
            # A flag SYN estar setada significa que é um cliente tentando estabelecer uma conexão nova
            # TODO: talvez você precise passar mais coisas para o construtor de conexão
            seq = random.randint(1, 9999999)
            conexao = self.conexoes[id_conexao] = Conexao(
                self, id_conexao, seq_no + 1, seq + 1)
            # TODO: você precisa fazer o handshake aceitando a conexão. Escolha se você acha melhor
            # fazer aqui mesmo ou dentro da classe Conexao.
            header = make_header(new_src_port, new_dst_port, seq,
                                 seq_no + 1, FLAGS_SYN | FLAGS_ACK)
            header = fix_checksum(header, new_src_addr, new_dst_addr)
            self.rede.enviar(header, new_dst_addr)
            if self.callback:
                self.callback(conexao)
        elif id_conexao in self.conexoes:
            # Passa para a conexão adequada se ela já estiver estabelecida
            self.conexoes[id_conexao]._rdt_rcv(seq_no, ack_no, flags, payload)
        else:
            print('%s:%d -> %s:%d (pacote associado a conexão desconhecida)' %
                  (src_addr, src_port, dst_addr, dst_port))


class Conexao:
    def __init__(self, servidor, id_conexao, seq_no, ack_no):
        self.servidor = servidor
        self.id_conexao = id_conexao
        self.callback = None
        self.seq_no = seq_no
        self.ack_no = ack_no
        # um timer pode ser criado assim; esta linha é só um exemplo e pode ser removida
        self.timer = None
        self.buffer = []
        self.sendedMessageTime = None
        self.SampleRTT = None
        self.DevRTT = None
        self.EstimatedRTT = None
        self.TimeoutInterval = 1
        # self.timer = asyncio.get_event_loop().call_later(1, self._exemplo_timer)
        # self.timer.cancel()   # é possível cancelar o timer chamando esse método; esta linha é só um exemplo e pode ser removida

    def stop_timer(self):
        if self.timer:
            self.timer.cancel()
            self.timer = None

    def start_timer(self):
        self.stop_timer()
        self.timer = asyncio.get_event_loop().call_later(
            self.TimeoutInterval, self._exemplo_timer)

    def _exemplo_timer(self):
        # Esta função é só um exemplo e pode ser removida
        self.servidor.rede.enviar(self.buffer[0], self.id_conexao[2])
        self.sendedMessageTime = None
        self.start_timer()
        # print('Este é um exemplo de como fazer um timer')

    def _rdt_rcv(self, seq_no, ack_no, flags, payload):
        # TODO: trate aqui o recebimento de segmentos provenientes da camada de rede.
        # Chame self.callback(self, dados) para passar dados para a camada de aplicação após
        # garantir que eles não sejam duplicados e que tenham sido recebidos em ordem.
        if (seq_no > self.seq_no - 1 and ((flags & FLAGS_ACK) == FLAGS_ACK)):

            if(self.sendedMessageTime is not None):
                self.SampleRTT = time.time() - self.sendedMessageTime
                if((self.DevRTT is None) | (self.EstimatedRTT is None)):
                    self.EstimatedRTT = self.SampleRTT
                    self.DevRTT = self.SampleRTT / 2
                else:
                    self.EstimatedRTT = ((1 - 0.125) *
                                         self.EstimatedRTT) + (0.125 * self.SampleRTT)
                    self.DevRTT = ((1 - 0.25) * self.DevRTT) + (0.25 *
                                                                abs(self.SampleRTT - self.EstimatedRTT))
                self.TimeoutInterval = self.EstimatedRTT + (4*self.DevRTT)
            if len(self.buffer) > 0:
                self.buffer.pop(0)
                if len(self.buffer) == 0:
                    self.stop_timer()
                else:
                    self.start_timer()
        if(seq_no != self.seq_no):
            return

        (src_addr, src_port, dst_addr, dst_port) = self.id_conexao

        new_src_addr = dst_addr
        new_dst_addr = src_addr

        new_src_port = dst_port
        new_dst_port = src_port

        if (flags & FLAGS_FIN) == FLAGS_FIN:
            self.seq_no += 1

            header = make_header(new_src_port, new_dst_port, ack_no,
                                 self.seq_no, FLAGS_ACK)
            header = fix_checksum(header, new_src_addr, new_dst_addr)
            self.servidor.rede.enviar(header, new_dst_addr)
            self.callback(self, b'')

        self.callback(self, payload)
        if(len(payload) != 0):
            self.seq_no += len(payload)

            header = make_header(new_src_port, new_dst_port, ack_no,
                                 self.seq_no, flags | FLAGS_ACK)
            header = fix_checksum(header, new_src_addr, new_dst_addr)
            self.servidor.rede.enviar(header, new_dst_addr)
            print('recebido payload: %r' % payload)

    # Os métodos abaixo fazem parte da API

    def registrar_recebedor(self, callback):
        """
        Usado pela camada de aplicação para registrar uma função para ser chamada
        sempre que dados forem corretamente recebidos
        """
        self.callback = callback

    def enviar(self, dados):
        """
        Usado pela camada de aplicação para enviar dados
        """
        # TODO: implemente aqui o envio de dados.
        # Chame self.servidor.rede.enviar(segmento, dest_addr) para enviar o segmento
        # que você construir para a camada de rede.
        if(len(dados) > MSS):
            self.enviar(dados[:MSS])
            self.enviar(dados[MSS:])
        else:
            (src_addr, src_port, dst_addr, dst_port) = self.id_conexao

            new_src_addr = dst_addr
            new_dst_addr = src_addr

            new_src_port = dst_port
            new_dst_port = src_port

            header = make_header(new_src_port, new_dst_port, self.ack_no,
                                 self.seq_no, FLAGS_ACK)
            header = fix_checksum(header+dados, new_src_addr, new_dst_addr)
            self.sendedMessageTime = time.time()
            self.servidor.rede.enviar(header, new_dst_addr)

            self.ack_no += len(dados)
            self.buffer.append(header)

        if not self.timer:
            self.start_timer()

    def fechar(self):
        """
        Usado pela camada de aplicação para fechar a conexão
        """
        # TODO: implemente aqui o fechamento de conexão
        (src_addr, src_port, dst_addr, dst_port) = self.id_conexao
        del self.servidor.conexoes[self.id_conexao]

        new_src_addr = dst_addr
        new_dst_addr = src_addr

        new_src_port = dst_port
        new_dst_port = src_port

        header = make_header(new_src_port, new_dst_port, self.ack_no,
                             self.seq_no, FLAGS_FIN)
        header = fix_checksum(header, new_src_addr, new_dst_addr)
        self.servidor.rede.enviar(header, new_dst_addr)
        pass
